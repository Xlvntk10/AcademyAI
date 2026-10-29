"""Модели персонального IELTS-тренажёра. Аккаунты пока не нужны."""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, Relationship, SQLModel


class Skill(SQLModel, table=True):
    """Один из четырёх навыков IELTS."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)  # Listening, Reading, Writing, Speaking
    description: str = ""
    lessons: list["Lesson"] = Relationship(back_populates="skill")


class Lesson(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(foreign_key="skill.id", index=True)
    title: str = Field(index=True)
    level: str = "A2"
    exercises: list["Exercise"] = Relationship(back_populates="lesson")
    skill: Optional[Skill] = Relationship(back_populates="lessons")


class Exercise(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    question: str
    correct_answer: str
    points: int = Field(default=10, ge=0)
    lesson: Optional[Lesson] = Relationship(back_populates="exercises")
    attempts: list["Attempt"] = Relationship(back_populates="exercise")


class Attempt(SQLModel, table=True):
    """Моя попытка выполнить упражнение: один локальный пользователь."""
    id: Optional[int] = Field(default=None, primary_key=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True)
    answer: str
    is_correct: bool
    earned_points: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exercise: Optional[Exercise] = Relationship(back_populates="attempts")
