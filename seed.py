"""Создание локальной БД и демонстрационных данных Academy AI."""
from sqlmodel import Session, select
from app.database.db import engine, init_db
from app.database.models import Skill, Lesson, Exercise, Attempt


def seed():
    init_db()
    with Session(engine) as session:
        if session.exec(select(Skill)).first() is not None:
            print("Тестовые данные уже добавлены.")
            return

        skills = [
            Skill(name="Listening", description="Понимание речи на слух"),
            Skill(name="Reading", description="Чтение и анализ текста"),
            Skill(name="Writing", description="Письменные задания и эссе"),
            Skill(name="Speaking", description="Разговорная практика"),
        ]
        session.add_all(skills)
        session.flush()

        lessons = [
            Lesson(skill_id=skills[0].id, title="Travel announcements", level="A2"),
            Lesson(skill_id=skills[1].id, title="Daily routine vocabulary", level="A2"),
            Lesson(skill_id=skills[2].id, title="Essay structure", level="B1"),
            Lesson(skill_id=skills[3].id, title="Speaking Part 1: hobbies", level="A2"),
        ]
        session.add_all(lessons)
        session.flush()

        exercises = [
            Exercise(lesson_id=lessons[0].id, question="Translate 'поворот налево'", correct_answer="turn left"),
            Exercise(lesson_id=lessons[1].id, question="Choose a synonym for 'quick'", correct_answer="fast"),
            Exercise(lesson_id=lessons[1].id, question="Opposite of 'early'?", correct_answer="late"),
            Exercise(lesson_id=lessons[2].id, question="Name the opening part of an essay", correct_answer="introduction"),
            Exercise(lesson_id=lessons[3].id, question="Translate 'хобби'", correct_answer="hobby"),
        ]
        session.add_all(exercises)
        session.flush()

        attempts = [
            Attempt(exercise_id=exercises[0].id, answer="turn left", is_correct=True, earned_points=10),
            Attempt(exercise_id=exercises[1].id, answer="fast", is_correct=True, earned_points=10),
            Attempt(exercise_id=exercises[2].id, answer="slow", is_correct=False, earned_points=0),
            Attempt(exercise_id=exercises[3].id, answer="introduction", is_correct=True, earned_points=10),
            Attempt(exercise_id=exercises[4].id, answer="hobby", is_correct=True, earned_points=10),
        ]
        session.add_all(attempts)
        session.commit()
        print("Готово: 4 навыка, 4 урока, 5 упражнений, 5 личных попыток.")


if __name__ == "__main__":
    seed()
