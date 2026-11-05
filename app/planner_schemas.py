from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Accept round-tripped read metadata, but never persist it as a setting.
    sync_revision: str | None = Field(default=None, exclude=True)
    available_minutes: list[int] = Field(min_length=7, max_length=7)
    daily_goal_minutes: int = Field(ge=5, le=480)
    weekly_goal_minutes: int = Field(ge=5, le=3360)
    reminder_enabled: bool = False
    reminder_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    english_percent: int = Field(default=65, ge=0, le=100, strict=True)
    monthly_goal_minutes: int = Field(default=900, ge=5, le=14880, strict=True)
    target_month: str | None = Field(default=None, pattern=r"^20\d{2}-(?:0[1-9]|1[0-2])$")
    reminder_days: list[Annotated[int, Field(ge=0, le=6, strict=True)]] = Field(default_factory=lambda: list(range(7)), max_length=7)
    masters_target_date: date | None = None

    @field_validator("available_minutes", mode="before")
    @classmethod
    def validate_minutes(cls, value):
        if not isinstance(value, list) or any(type(v) is not int or not 0 <= v <= 480 for v in value):
            raise ValueError("Укажите от 0 до 480 целых минут на каждый день")
        return value


class SettingsRead(SettingsInput):
    timezone: str
    sync_revision: str | None = Field(default=None, exclude=False)


class GenerateWeek(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_start: date
    replace_pending: bool = False


class AdaptWeek(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_start: date


class ReminderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reminder_enabled: bool
    reminder_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reminder_days: list[Annotated[int, Field(ge=0, le=6, strict=True)]] = Field(default_factory=lambda: list(range(7)), max_length=7)


class CompleteTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actual_minutes: int = Field(ge=1, le=480)


class RescheduleTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled_date: date


class TaskRead(BaseModel):
    sync_revision: str | None = None
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
    sync_revision: str | None = None
    week_start: date
    today: date
    generated: bool
    settings: SettingsRead
    tasks: list[TaskRead]
    overdue: list[TaskRead]
    planned_minutes: int
    completed_minutes: int
