"""Подключение к локальной SQLite базе данных."""
from pathlib import Path
from sqlalchemy import event
from sqlmodel import SQLModel, create_engine

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = f"sqlite:///{(ROOT / 'database.db').as_posix()}"
engine = create_engine(DATABASE_URL, echo=True, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def enable_foreign_keys(connection, _):
    """SQLite проверяет внешние ключи только после включения PRAGMA."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db():
    from app.database import models  # noqa: F401 — регистрируем таблицы
    SQLModel.metadata.create_all(engine)
