from datetime import datetime
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from app.schemas import LessonDetail, RunRead, SubmitAnswer


class OfflineBundle(BaseModel):
    protocol: int = 1
    server_id: str
    content_hash: str
    downloaded_at: datetime
    lesson: LessonDetail


class OfflineSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: int = Field(default=1, ge=1, le=1, strict=True)
    attempt_id: UUID
    server_id: UUID
    lesson_slug: str = Field(min_length=1, max_length=100)
    content_version: int = Field(gt=0, strict=True)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    started_at: AwareDatetime
    completed_at: AwareDatetime
    answers: list[SubmitAnswer] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_attempt(self):
        if self.completed_at < self.started_at:
            raise ValueError("Время завершения раньше начала")
        if len({a.exercise_id for a in self.answers}) != len(self.answers):
            raise ValueError("Упражнения в попытке должны быть уникальными")
        return self


class OfflineAcknowledgement(BaseModel):
    attempt_id: str
    received_at: datetime
    result: RunRead
