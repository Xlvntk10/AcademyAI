from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available_minutes: list[int] = Field(min_length=7, max_length=7)
    daily_goal_minutes: int = Field(ge=5, le=480)
    weekly_goal_minutes: int = Field(ge=5, le=3360)
    reminder_enabled: bool = False
    reminder_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @field_validator("available_minutes", mode="before")
    @classmethod
    def validate_minutes(cls, value):
        if not isinstance(value, list) or any(type(v) is not int or not 0 <= v <= 480 for v in value):
            raise ValueError("Укажите от 0 до 480 целых минут на каждый день")
        return value


class SettingsRead(SettingsInput):
    timezone: str
    english_percent: int = 65


class GenerateWeek(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_start: date
    replace_pending: bool = False


class CompleteTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actual_minutes: int = Field(ge=1, le=480)


class RescheduleTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled_date: date


class TaskRead(BaseModel):
    id: str
    scheduled_date: date
    original_date: date
    subject: Literal["english", "python"]
    kind: Literal["lesson", "review", "practice"]
    title: str
    instructions: str
    planned_minutes: int
    status: str
    actual_minutes: int | None
    completed_at: datetime | None
    lesson_slug: str | None
    overdue: bool


class WeekRead(BaseModel):
    week_start: date
    today: date
    generated: bool
    settings: SettingsRead
    tasks: list[TaskRead]
    overdue: list[TaskRead]
    planned_minutes: int
    completed_minutes: int
