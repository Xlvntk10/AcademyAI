from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, strict=True)
    answers: dict[str, Annotated[str, Field(max_length=500)]] = Field(default_factory=dict, max_length=30)
    text: str = Field(default="", max_length=20000)
    mode: Literal["text", "audio"] = "text"


class IeltsRunRead(BaseModel):
    id: str
    test_id: str
    title: str
    section: str
    started_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    revision: int
    answers: dict[str, str]
    text: str
    mode: str
    result: dict | None
