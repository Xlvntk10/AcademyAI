from datetime import date
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class WordRead(BaseModel):
    id: int
    term: str
    translation: str
    example: str
    lesson_slug: str
    unlocked: bool
    added: bool
    due_on: date | None
    box: int
    review_count: int
    correct_count: int


class VocabularyRead(BaseModel):
    today: date
    words: list[WordRead]
    due_count: int
    added_count: int


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    answer: str = Field(min_length=1, max_length=100)


class ReviewRead(BaseModel):
    id: str
    card_id: int
    answer: str
    is_correct: bool
    correct_answer: str
    example: str
    due_on: date
    box: int
