"""Read-only PostgreSQL connectivity probe. No application imports or migrations.

The URI prompt is visible and accepts only [YOUR-DATABASE-PASSWORD].
The real password uses a hidden prompt; DATABASE_URL mode is never echoed.
Only SELECT 1 is executed, in a read-only transaction which is rolled back.
"""
import argparse
from contextlib import contextmanager, ExitStack
import getpass
import logging
import os
import re
import ssl
import shutil
import tempfile
from pathlib import Path
import sys
import warnings

import psycopg
from sqlalchemy.engine import URL, make_url


PASSWORD_PLACEHOLDER = "[YOUR-DATABASE-PASSWORD]"


class ConfigurationError(ValueError):
    """Messages in this class must never contain user-supplied values."""


MESSAGES = {
    "AUTH_REJECTED": "Сервер отклонил пользователя/пароль. Проверь пароль БД и пользователя с суффиксом проекта; это не пароль аккаунта Supabase и не API key.",
    "POOLER_IDENTITY": "Pooler не нашёл проект или пользователя. Заново скопируй host и username из Connect → Session pooler; смена пароля сама по себе не исправляет эту ошибку.",
    "TLS_HOSTNAME": "Имя сервера не совпадает с сертификатом. Проверь host из URI; не заменяй его IP-адресом.",
    "TLS_CERTIFICATE": "Не прошла проверка сертификата сервера. Возможны неверный CA, неполная цепочка, истёкший сертификат или неверное время компьютера. TLS не отключён.",
    "TLS_CA_LOAD": "Драйвер не смог загрузить корневой сертификат. Проверь доступ к CA-файлу и его PEM-формат.",
    "TLS_REQUIRED": "Сервер не согласовал обязательный TLS. Соединение без TLS запрещено; SELECT 1 не выполнялся.",
    "TLS_HANDSHAKE": "Ошибка согласования TLS. Проверь endpoint, сертификаты и сетевой фильтр; проверки TLS сохранены.",
    "DNS": "Не удалось определить адрес сервера по имени. Проверь host из Session pooler URI и DNS.",
    "TIMEOUT": "Истекло время ожидания. Доступность TCP-порта не подтверждает успешный TLS или ответ PostgreSQL; проверь активность проекта и сеть.",
    "CONNECTION_REFUSED": "Соединение отклонено. Проверь endpoint, порт 5432, активность проекта и ограничения сети.",
    "NETWORK": "Соединение оборвано или сеть недоступна. Проверь VPN, сетевой фильтр и доступность проекта.",
    "DATABASE": "Сервер сообщил, что база не существует. Проверь имя базы из URI (обычно postgres).",
    "ACCESS_RULE": "Сервер запретил вход правилом доступа. Проверь разрешённые сети, роль и настройки проекта.",
    "PERMISSION": "Сервер отклонил операцию из-за недостатка прав роли.",
    "POOL_LIMIT": "Исчерпан лимит соединений pooler/базы. Закрой лишние подключения и повтори позже.",
    "SERVER_UNAVAILABLE": "Сервер ещё не готов или временно недоступен. Проверь состояние проекта и повтори позже.",
    "AUTH_PROTOCOL": "Сбой серверной процедуры аутентификации. Это не доказательство неверного пароля; проверь состояние pooler и проекта.",
    "SELECT_RESULT": "Соединение установлено, но SELECT 1 вернул неожиданный результат.",
    "UNKNOWN": "Причина не распознана безопасным классификатором. Это не доказательство неверного пароля. Исходная ошибка скрыта; передай только код и этап этой диагностики.",
}


def diagnose(error: Exception) -> str:
    # Inspect internally, but NEVER print a fragment, URL, repr or chained traceback.
    state = getattr(error, "sqlstate", None)
    states = {"28P01":"AUTH_REJECTED", "3D000":"DATABASE", "42501":"PERMISSION",
              "53300":"POOL_LIMIT", "57P03":"SERVER_UNAVAILABLE"}
    if isinstance(state, str) and state in states:
        return states[state]
    detail = str(error).lower()
    rules = [
        ("POOLER_IDENTITY", ("tenant or user not found", "tenant/user", "tenant not found")),
        ("TLS_HOSTNAME", ("does not match host name", "hostname mismatch", "host name mismatch")),
        ("TLS_CA_LOAD", ("root certificate file", "could not read root certificate", "could not load root certificate")),
        ("TLS_CERTIFICATE", ("certificate verify failed", "certificate verification failed", "self-signed certificate", "certificate has expired", "unable to get local issuer certificate")),
        ("TLS_REQUIRED", ("server does not support ssl", "ssl is not enabled", "ssl connection is required")),
        ("AUTH_REJECTED", ("password authentication failed", "no password supplied")),
        ("AUTH_PROTOCOL", ("sasl authentication failed", "authentication query failed", "scram authentication failed")),
        ("ACCESS_RULE", ("no pg_hba.conf entry",)),
        ("POOL_LIMIT", ("maxclientsinsessionmode", "max client connections", "too many clients", "remaining connection slots")),
        ("DNS", ("could not translate host name", "getaddrinfo failed", "name or service not known", "nodename nor servname")),
        ("TIMEOUT", ("timeout expired", "connection timeout", "timed out")),
        ("CONNECTION_REFUSED", ("connection refused", "actively refused")),
        ("NETWORK", ("network is unreachable", "no route to host", "connection reset", "server closed the connection", "ssl syscall error: eof")),
        ("TLS_HANDSHAKE", ("ssl error", "tls error", "ssl handshake", "tls handshake")),
    ]
    for code, needles in rules:
        if any(needle in detail for needle in needles):
            return code
    return "ACCESS_RULE" if state == "28000" else "UNKNOWN"


class ProbeFailure(RuntimeError):
    def __init__(self, stage, code):
        self.stage, self.code = stage, code
        super().__init__(code)


def unquote(value: str) -> str:
    value = value.strip()
    pairs = {'"':'"', "'":"'", '“':'”', '‘':'’'}
    if len(value) >= 2 and value[0] in pairs and value[-1] == pairs[value[0]]:
        return value[1:-1].strip()
    return value


def certificate_path(value: Path | str) -> Path:
    # Read-Host preserves pasted outer quotes. Strip one matching pair, never
    # strip arbitrary characters or alter passwords.
    try:
        path = Path(unquote(str(value))).expanduser().resolve(strict=True)
        if not path.is_file():
            raise FileNotFoundError
        # Parse the file locally before DNS/TLS/auth. A successful Test-Path alone
        # does not establish that the contents are a CA certificate in PEM format.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(path))
        return path
    except FileNotFoundError:
        raise ConfigurationError("[CA_PATH] CA-файл не найден. Проверь полный путь; внешние парные кавычки теперь удаляются автоматически.") from None
    except PermissionError:
        raise ConfigurationError("[CA_ACCESS] Нет доступа к CA-файлу. Проверь права чтения.") from None
    except ssl.SSLError:
        raise ConfigurationError("[CA_FORMAT] Файл найден, но не читается как CA-сертификат PEM. Скачай CA из Database Settings; файл должен содержать BEGIN CERTIFICATE, а не HTML или ключ.") from None
    except (OSError, ValueError):
        raise ConfigurationError("[CA_PATH] Некорректный путь к CA-файлу. Проверь парность кавычек и имя файла.") from None


def database_url(uri: str, password: str | None, ca_file: Path | str) -> URL:
    try:
        parsed = make_url(unquote(uri))
        if parsed.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError
        if not parsed.host or not parsed.username or not parsed.database:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.host):
            raise ValueError
        if (parsed.port or 5432) != 5432:
            raise ConfigurationError("[URI_PORT] Нужен Session pooler с портом 5432, не Transaction pooler.")
        if parsed.host.endswith(".pooler.supabase.com") and "." not in parsed.username:
            raise ConfigurationError("[URI_USER] В username Session pooler нужен суффикс проекта. Скопируй URI целиком из Connect.")
        if set(parsed.query) - {"sslmode", "sslrootcert"}:
            raise ConfigurationError("[URI_OPTIONS] URI содержит неподдерживаемые параметры. Оставь только sslmode и sslrootcert либо URI без параметров.")
        if parsed.query.get("sslmode", "verify-full") != "verify-full":
            raise ConfigurationError("[TLS_MODE] Для проверки требуется sslmode=verify-full. Удали другой sslmode из URI или замени его на verify-full.")
        secret = password if password is not None else parsed.password
        if not secret or secret in {PASSWORD_PLACEHOLDER, "[YOUR-PASSWORD]", "[YOUR_PASSWORD]", "YOUR-PASSWORD"}:
            raise ConfigurationError("[PASSWORD_MISSING] Нужен настоящий пароль базы, не placeholder и не API key.")
    except ConfigurationError:
        raise
    except Exception:
        raise ConfigurationError("[URI_FORMAT] Не удалось разобрать PostgreSQL URI. Скопируй Session pooler URI с placeholder пароля; настоящий пароль вводи отдельно без URL-кодирования.") from None
    certificate = certificate_path(ca_file)
    return URL.create("postgresql+psycopg", username=parsed.username, password=secret,
        host=parsed.host, port=5432, database=parsed.database,
        query={"sslmode": "verify-full", "sslrootcert": certificate.as_posix()})


@contextmanager
def driver_certificate(path: str):
    # Windows libpq may pass UTF-8 file names to an ANSI fopen. Python can read
    # the same certificate while libpq reports "No such file". Copy ONLY the
    # public CA bytes to an ASCII temporary path; keep verify-full unchanged.
    if os.name != "nt" or path.isascii():
        yield path
        return
    with tempfile.TemporaryDirectory(prefix="academy-ca-") as directory:
        target = Path(directory) / "root.pem"
        if not str(target).isascii():
            raise ConfigurationError("[CA_PATH_ENCODING] Драйвер Windows не поддержал путь CA. Сохрани публичный CA-сертификат в папку с латинским путём и укажи её.")
        try:
            shutil.copyfile(path, target)
        except OSError:
            raise ConfigurationError("[CA_TEMP_COPY] Не удалось подготовить временную копию публичного CA. Проверь права чтения и доступ к временной папке.") from None
        yield str(target)


def check_connection(url: URL) -> None:
    # Explicit kwargs prevent URI query parameters or PGOPTIONS from injecting SQL.
    # No SQLAlchemy engine initialization, ORM callbacks or application startup.
    connection = None
    resources = ExitStack()
    stage = "CONNECT"
    try:
        ca_file = resources.enter_context(driver_certificate(url.query["sslrootcert"]))
        connection = psycopg.connect(host=url.host, port=url.port, dbname=url.database,
            user=url.username, password=url.password, sslmode="verify-full",
            sslrootcert=ca_file, ssl_min_protocol_version="TLSv1.2",
            gssencmode="disable", options="", application_name="academy-connection-check",
            connect_timeout=15, prepare_threshold=None, autocommit=False)
        stage = "TLS"
        if not connection.pgconn.ssl_in_use:
            raise ProbeFailure(stage, "TLS_REQUIRED")
        stage = "SELECT"
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise ProbeFailure(stage, "SELECT_RESULT")
        stage = "ROLLBACK"
        connection.rollback()
    except (ProbeFailure, ConfigurationError):
        raise
    except Exception as error:
        raise ProbeFailure(stage, diagnose(error)) from None
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            resources.close()


def hidden(prompt: str) -> str:
    # Refuse getpass's echoing fallback if run without a usable terminal.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def visible_uri() -> str:
    # Terminal echo happens while typing. Validate immediately, never repeat the
    # line or include it in errors. Only a literal placeholder is accepted here.
    uri = input("Session pooler URI (видимый ввод; только с [YOUR-DATABASE-PASSWORD], без настоящего пароля): ")
    try:
        value = unquote(uri)
        prefix = r"^(?:postgres|postgresql|postgresql\+psycopg)://[^:/@?#\s]+:\[YOUR-DATABASE-PASSWORD\]@"
        if not re.match(prefix, value) or make_url(value).password != PASSWORD_PLACEHOLDER:
            raise ValueError
        return value
    except Exception:
        raise ConfigurationError("[URI_PLACEHOLDER] URI не принят. В поле пароля должен быть только [YOUR-DATABASE-PASSWORD]. Настоящий пароль вводится отдельно скрыто; строка не повторяется и подключение не выполняется.") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-file", required=True, help="Trusted Supabase CA certificate downloaded from Database Settings")
    parser.add_argument("--from-env", action="store_true", help="Read DATABASE_URL instead of prompting; ignores ACADEMY_DATABASE_URL")
    args = parser.parse_args(argv)
    # No driver debug logs or raw exception strings: these may contain credentials.
    logging.disable(logging.CRITICAL)
    try:
        if args.from_env:
            uri, password = os.environ.get("DATABASE_URL", ""), None
            if not uri:
                raise ConfigurationError("DATABASE_URL не задана. Запусти без --from-env: URI вводится с плейсхолдером, пароль отдельно скрыто.")
        else:
            uri = visible_uri()
            password = hidden("Пароль базы PostgreSQL (ввод скрыт, без URL-кодирования): ")
        url = database_url(uri, password, args.ca_file)
        print("OK [CONFIG]: URI разобран; CA-файл найден и прочитан. Проверка TLS: verify-full.", flush=True)
        check_connection(url)
        print("OK: psycopg " + psycopg.__version__ + "; TLS включён, сертификат и имя сервера проверены (verify-full).")
        print("SELECT 1 = 1. Транзакция только для чтения завершена откатом. Миграции не запускались.")
        return 0
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
    except ProbeFailure as error:
        print(f"FAIL [{error.stage}/{error.code}]: {MESSAGES[error.code]}", file=sys.stderr)
    except getpass.GetPassWarning:
        print("Нужен обычный интерактивный PowerShell для скрытого ввода. Не передавай пароль аргументом команды.", file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print("Проверка отменена.", file=sys.stderr)
        return 130
    except Exception as error:
        print("FAIL [CHECK/" + diagnose(error) + "]: " + MESSAGES[diagnose(error)], file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
