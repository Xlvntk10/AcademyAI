"""Проверка данных в персональном IELTS-тренажёре."""
from sqlmodel import Session, select
from sqlalchemy import inspect, text
from app.database.db import engine, init_db
from app.database.models import Skill, Lesson, Exercise, Attempt


def show():
    init_db()
    schema = inspect(engine)
    with Session(engine) as session:
        if session.exec(text("PRAGMA foreign_keys")).scalar_one() != 1:
            raise RuntimeError("Проверка внешних ключей SQLite выключена")
        if session.exec(text("PRAGMA integrity_check")).scalar_one() != "ok":
            raise RuntimeError("Нарушена целостность SQLite")
        if session.exec(text("PRAGMA foreign_key_check")).all():
            raise RuntimeError("Найдены ссылки на отсутствующие записи")
        for model in (Skill, Lesson, Exercise, Attempt):
            table = model.__tablename__
            if schema.get_pk_constraint(table)["constrained_columns"] != ["id"]:
                raise RuntimeError(f"Некорректный первичный ключ: {table}")
            expected_fks = {
                (fk.parent.name, fk.column.table.name, fk.column.name)
                for fk in model.__table__.foreign_keys
            }
            actual_fks = {
                (fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0])
                for fk in schema.get_foreign_keys(table)
            }
            if actual_fks != expected_fks:
                raise RuntimeError(f"Некорректные внешние ключи: {table}")
            rows = session.exec(select(model)).all()
            if not rows:
                raise RuntimeError(f"Таблица {table} пуста: сначала запустите seed.py")
            print(f"\n{model.__name__}: {len(rows)} записей")
            for row in rows:
                print("  ", row.model_dump())
        for skill in session.exec(select(Skill)).all():
            for lesson in skill.lessons:
                if lesson.skill is not skill:
                    raise RuntimeError("Нарушена связь Skill — Lesson")
                for exercise in lesson.exercises:
                    if exercise.lesson is not lesson:
                        raise RuntimeError("Нарушена связь Lesson — Exercise")
                    for attempt in exercise.attempts:
                        if attempt.exercise is not exercise:
                            raise RuntimeError("Нарушена связь Exercise — Attempt")
        print("\nOK: PK, FK, целостность SQLite и двусторонние ORM-связи проверены.")


if __name__ == "__main__":
    show()
