from datetime import date
from pydantic import BaseModel


class DailyActivity(BaseModel):
    date: date
    answers: int
    correct_answers: int
    completed_runs: int
    tasks: int
    minutes: int
    practice_xp: int
    vocabulary_reviews: int


class SubjectStats(BaseModel):
    subject: str
    completed_lessons: int
    available_lessons: int
    answers: int
    correct_answers: int
    accuracy: float | None
    minutes: int
    lesson_xp: int


class Achievement(BaseModel):
    code: str
    title: str
    description: str
    target: int
    progress: int
    unlocked_on: date | None
    reward: str


class Goal(BaseModel):
    target_minutes: int
    completed_minutes: int
    reached: bool


class WeeklyReport(BaseModel):
    start: date
    end: date
    active_days: int
    minutes: int
    completed_runs: int
    answers: int
    correct_answers: int
    accuracy: float | None
    english_minutes: int
    python_minutes: int


class Dashboard(BaseModel):
    today: date
    timezone: str
    total_xp: int
    lesson_xp: int
    practice_xp: int
    level: int
    level_title: str
    xp_in_level: int
    xp_to_next_level: int
    current_streak: int
    longest_streak: int
    completed_lessons: int
    completed_runs: int
    answers: int
    correct_answers: int
    accuracy: float | None
    minutes: int
    daily_goal: Goal
    weekly_goal: Goal
    subjects: list[SubjectStats]
    achievements: list[Achievement]
    activity: list[DailyActivity]
    weekly_report: WeeklyReport
