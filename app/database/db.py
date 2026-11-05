"""SQLite development and account-scoped PostgreSQL transactions."""
from pathlib import Path
import os
from sqlalchemy import event, text
from sqlalchemy.orm import Session as SASession
from sqlmodel import SQLModel, create_engine

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get("ACADEMY_DATABASE_URL") or os.environ.get("DATABASE_URL") or f"sqlite:///{(ROOT / 'database.db').as_posix()}"


def enable_foreign_keys(connection, _):
    """SQLite проверяет внешние ключи только после включения PRAGMA."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url=DATABASE_URL):
    if url.startswith(("postgres://", "postgresql://")):
        url = "postgresql+psycopg://" + url.split("://", 1)[1]
    if url.startswith("postgresql+"):
        return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, hide_parameters=True,
                             connect_args={"prepare_threshold": None, "connect_timeout": 15})
    result = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    event.listen(result, "connect", enable_foreign_keys)
    return result


@event.listens_for(SASession, "after_begin")
def account_transaction(session, transaction, connection):
    if connection.dialect.name == "postgresql":
        user_id = (session.info.get("account") or {}).get("id", "")
        connection.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user_id})
        connection.execute(text("SET LOCAL search_path TO academy, public"))
        connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))


def begin_write(session):
    if session.get_bind().dialect.name == "sqlite":
        session.exec(text("BEGIN IMMEDIATE"))
    else:
        user_id = session.info["account"]["id"]
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:user_id, 0))"), {"user_id": user_id})


engine = make_engine()


def init_db():
    if engine.dialect.name == "postgresql":
        raise RuntimeError("Use scripts.migrate_cloud for PostgreSQL schema changes")
    from app.database import models  # noqa: F401 — регистрируем таблицы
    SQLModel.metadata.create_all(engine)
