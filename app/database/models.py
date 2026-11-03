"""Модели персонального IELTS-тренажёра. Аккаунты пока не нужны."""
from datetime import date, datetime, timezone
from typing import Optional
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import Column, JSON, UniqueConstraint


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


# V2 adds tables without changing the four original tables or their data.
class LessonContent(SQLModel, table=True):
    lesson_id: int = Field(primary_key=True, foreign_key="lesson.id")
    slug: str = Field(unique=True, index=True)
    summary: str
    duration_minutes: int
    version: int = 1
    theory: list[dict] = Field(sa_column=Column(JSON, nullable=False))


class ExerciseContent(SQLModel, table=True):
    exercise_id: int = Field(primary_key=True, foreign_key="exercise.id")
    position: int
    kind: str
    options: list[str] = Field(sa_column=Column(JSON, nullable=False))
    explanation: str
    accepted_answers: list[str] = Field(sa_column=Column(JSON, nullable=False))
    case_sensitive: bool = False


class LessonRun(SQLModel, table=True):
    id: str = Field(primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    content_version: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class RunAnswer(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("run_id", "exercise_id", name="uq_run_exercise"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="lessonrun.id", index=True)
    exercise_id: int = Field(foreign_key="exercise.id")
    attempt_id: int = Field(foreign_key="attempt.id", unique=True)


class LessonMeta(SQLModel, table=True):
    lesson_id: int = Field(primary_key=True, foreign_key="lesson.id")
    subject: str = Field(index=True)
    topic: str
    position: int


class StudySettings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    available_minutes: list[int] = Field(default_factory=lambda: [90, 90, 90, 90, 90, 180, 180], sa_column=Column(JSON, nullable=False))
    daily_goal_minutes: int = 30
    weekly_goal_minutes: int = 210
    reminder_enabled: bool = False
    reminder_time: str = "19:00"
    timezone: str = "Asia/Almaty"


class PlanWeek(SQLModel, table=True):
    week_start: date = Field(primary_key=True)
    revision: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StudyTask(SQLModel, table=True):
    id: str = Field(primary_key=True)
    plan_week: date = Field(foreign_key="planweek.week_start", index=True)
    scheduled_date: date = Field(index=True)
    original_date: date
    subject: str
    kind: str
    title: str
    instructions: str
    planned_minutes: int
    lesson_id: Optional[int] = Field(default=None, foreign_key="lesson.id")
    status: str = "pending"
    actual_minutes: Optional[int] = None
    completed_at: Optional[datetime] = None
    completed_run_id: Optional[str] = Field(default=None, foreign_key="lessonrun.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskMove(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(foreign_key="studytask.id", index=True)
    from_date: date
    to_date: date
    moved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VocabularyCard(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    term: str = Field(unique=True)
    translation: str
    example: str


class VocabularyProgress(SQLModel, table=True):
    card_id: int = Field(primary_key=True, foreign_key="vocabularycard.id")
    box: int = 0
    due_on: date
    added_at: datetime
    review_count: int = 0
    correct_count: int = 0


class VocabularyReview(SQLModel, table=True):
    id: str = Field(primary_key=True)
    card_id: int = Field(foreign_key="vocabularycard.id", index=True)
    answer: str
    is_correct: bool
    reviewed_at: datetime
    due_on: date
    box: int


class LessonPrerequisite(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lesson_id", "prerequisite_id", name="uq_lesson_prerequisite"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    prerequisite_id: int = Field(foreign_key="lesson.id")
