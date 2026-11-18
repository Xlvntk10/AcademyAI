"""Read-only PostgreSQL connectivity probe. No application imports or migrations.

Credentials are accepted through hidden prompts or DATABASE_URL, never CLI args.
Only SELECT 1 is executed, in a read-only transaction which is rolled back.
"""
import argparse
import getpass
import logging
import os
from pathlib import Path
import sys
import warnings

import psycopg
from sqlalchemy.engine import URL, make_url


class ConfigurationError(ValueError):
    """Messages in this class must never contain user-supplied values."""


def database_url(uri: str, password: str | None, ca_file: Path) -> URL:
    try:
        parsed = make_url(uri.strip())
        if parsed.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError
        if not parsed.host or not parsed.username or not parsed.database:
            raise ValueError
        if (parsed.port or 5432) != 5432:
            raise ConfigurationError("Нужен Session pooler с портом 5432, не Transaction pooler.")
        if any(char.isspace() for char in parsed.host) or "," in parsed.host:
            raise ValueError
        if set(parsed.query) - {"sslmode", "sslrootcert"}:
            raise ConfigurationError("URI содержит неподдерживаемые параметры. Оставь только sslmode и sslrootcert либо URI без параметров.")
        if parsed.query.get("sslmode", "verify-full") != "verify-full":
            raise ConfigurationError("Для проверки требуется sslmode=verify-full. Удали другой sslmode из URI или замени его на verify-full.")
        secret = password if password is not None else parsed.password
        if not secret or secret in {"[YOUR-PASSWORD]", "[YOUR_PASSWORD]", "YOUR-PASSWORD"}:
            raise ConfigurationError("Нужен настоящий пароль базы, не placeholder и не API key.")
        certificate = ca_file.expanduser().resolve(strict=True)
        if not certificate.is_file():
            raise ValueError
        return URL.create("postgresql+psycopg", username=parsed.username, password=secret,
            host=parsed.host, port=5432, database=parsed.database,
            query={"sslmode": "verify-full", "sslrootcert": certificate.as_posix()})
    except ConfigurationError:
        raise
    except Exception:
        raise ConfigurationError("Не удалось прочитать PostgreSQL URI или CA-файл. Проверь формат URI и путь к скачанному сертификату.") from None


def check_connection(url: URL) -> None:
    # Explicit kwargs prevent URI query parameters or PGOPTIONS from injecting SQL.
    # No SQLAlchemy engine initialization, ORM callbacks or application startup.
    connection = psycopg.connect(host=url.host, port=url.port, dbname=url.database,
        user=url.username, password=url.password, sslmode="verify-full",
        sslrootcert=url.query["sslrootcert"], ssl_min_protocol_version="TLSv1.2",
        gssencmode="disable", options="", application_name="academy-connection-check",
        connect_timeout=15, prepare_threshold=None, autocommit=False)
    try:
        if not connection.pgconn.ssl_in_use:
            raise RuntimeError("TLS was not negotiated")
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("Unexpected probe result")
        connection.rollback()
    finally:
        # Closing also rolls back a failed transaction; there is no commit path.
        connection.close()


def hidden(prompt: str) -> str:
    # Refuse getpass's echoing fallback if run without a usable terminal.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-file", required=True, type=Path, help="Trusted Supabase CA certificate downloaded from Database Settings")
    parser.add_argument("--from-env", action="store_true", help="Read DATABASE_URL instead of prompting; ignores ACADEMY_DATABASE_URL")
    args = parser.parse_args(argv)
    # No driver debug logs or raw exception strings: these may contain credentials.
    logging.disable(logging.CRITICAL)
    try:
        if args.from_env:
            uri, password = os.environ.get("DATABASE_URL", ""), None
            if not uri:
                raise ConfigurationError("DATABASE_URL не задана. Запусти без --from-env для скрытого ввода.")
        else:
            uri = hidden("Session pooler URI (ввод скрыт; пароль в URI можно оставить placeholder): ")
            password = hidden("Пароль базы PostgreSQL (ввод скрыт, без URL-кодирования): ")
        url = database_url(uri, password, args.ca_file)
        check_connection(url)
        print("OK: psycopg " + psycopg.__version__ + "; TLS включён, сертификат и имя сервера проверены (verify-full).")
        print("SELECT 1 = 1. Транзакция только для чтения завершена откатом. Миграции не запускались.")
        return 0
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
    except getpass.GetPassWarning:
        print("Нужен обычный интерактивный PowerShell для скрытого ввода. Не передавай пароль аргументом команды.", file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print("Проверка отменена.", file=sys.stderr)
        return 130
    except Exception:
        print("Подключение не подтверждено. Проверь URI, пароль базы, CA-сертификат, доступность проекта и сеть. Подробности ошибки скрыты, чтобы не раскрыть реквизиты.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
