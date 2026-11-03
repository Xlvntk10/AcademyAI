"""Public API schemas deliberately exclude answer keys before submission."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class StartRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class SubmitAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    exercise_id: int = Field(gt=0)
    answer: str = Field(min_length=1, max_length=500)


class TheoryBlock(BaseModel):
    title: str
    body: str
    examples: list[str]
    code: str | None = None


class ExerciseRead(BaseModel):
    id: int
    question: str
    points: int
    position: int
    kind: Literal["choice", "text"]
    options: list[str]


class LessonRead(BaseModel):
    id: int
    slug: str
    title: str
    level: str
    summary: str
    duration_minutes: int
    version: int
    exercise_count: int
    max_score: int
    subject: str
    topic: str
    position: int
    unlocked: bool
    mastered: bool
    prerequisites: list[str]
    best_percent: float


class LessonDetail(LessonRead):
    theory: list[TheoryBlock]
    exercises: list[ExerciseRead]


class AnswerRead(BaseModel):
    exercise_id: int
    answer: str
    is_correct: bool
    earned_points: int
    correct_answer: str
    explanation: str


class RunRead(BaseModel):
    id: str
    lesson_slug: str
    started_at: datetime
    completed_at: datetime | None
    answered_count: int
    exercise_count: int
    score: int
    max_score: int
    correct_count: int
    answers: list[AnswerRead]


class LessonStats(BaseModel):
    slug: str
    completed_runs: int
    best_score: int
    max_score: int
    active_run_id: str | None
    last_result: RunRead | None


class ProgressRead(BaseModel):
    completed_lessons: int
    completed_runs: int
    total_xp: int
    lessons: list[LessonStats]
