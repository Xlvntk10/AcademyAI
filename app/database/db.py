"""Подключение к локальной SQLite базе данных."""
from pathlib import Path
import os
from sqlalchemy import event
from sqlmodel import SQLModel, create_engine

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get("ACADEMY_DATABASE_URL", f"sqlite:///{(ROOT / 'database.db').as_posix()}")


def enable_foreign_keys(connection, _):
    """SQLite проверяет внешние ключи только после включения PRAGMA."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url=DATABASE_URL):
    result = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    event.listen(result, "connect", enable_foreign_keys)
    return result


engine = make_engine()


def init_db():
    from app.database import models  # noqa: F401 — регистрируем таблицы
    SQLModel.metadata.create_all(engine)
