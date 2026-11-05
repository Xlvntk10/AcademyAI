from app.database.db import begin_write
"""A small deterministic review schedule, no AI and no farmable XP."""
from datetime import timedelta
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from app.database.models import LessonContent, LessonRun, VocabularyCard, VocabularyProgress, VocabularyReview
from app.routers.exercises import DB
from app.services import clock
from app.services.learning import normalize
from app.vocabulary_schemas import VocabularyRead, ReviewInput, ReviewRead

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])
INTERVALS = (1, 3, 7, 14, 30)


def catalogue(session):
    today = clock.local_day()
    unlocked = set(session.exec(select(LessonRun.lesson_id).where(LessonRun.completed_at.is_not(None))).all())
    states = {p.card_id: p for p in session.exec(select(VocabularyProgress)).all()}
    words = []
    for card, lesson in session.exec(select(VocabularyCard, LessonContent)
            .join(LessonContent, LessonContent.lesson_id == VocabularyCard.lesson_id).order_by(VocabularyCard.id)).all():
        state = states.get(card.id)
        words.append(dict(id=card.id, term=card.term, translation=card.translation, example=card.example,
            lesson_slug=lesson.slug, unlocked=card.lesson_id in unlocked, added=state is not None,
            due_on=state.due_on if state else None, box=state.box if state else 0,
            review_count=state.review_count if state else 0, correct_count=state.correct_count if state else 0))
    return dict(today=today, words=words, due_count=sum(p.due_on <= today for p in states.values()), added_count=len(states))


def get_card(session, card_id):
    card = session.get(VocabularyCard, card_id)
    if not card:
        raise HTTPException(404, "Слово не найдено")
    return card


@router.get("", response_model=VocabularyRead)
def read_vocabulary(session: DB):
    return catalogue(session)


@router.post("/{card_id}/add", response_model=VocabularyRead)
def add_word(card_id: int, session: DB):
    begin_write(session)
    card = get_card(session, card_id)
    completed = session.exec(select(LessonRun).where(LessonRun.lesson_id == card.lesson_id,
        LessonRun.completed_at.is_not(None))).first()
    if not completed:
        raise HTTPException(409, "Сначала заверши связанный урок")
    if not session.get(VocabularyProgress, card_id):
        session.add(VocabularyProgress(card_id=card_id, due_on=clock.local_day(), added_at=clock.now()))
        session.commit()
    return catalogue(session)


def review_read(card, review):
    return dict(id=review.id, card_id=card.id, answer=review.answer, is_correct=review.is_correct,
        correct_answer=card.term, example=card.example, due_on=review.due_on, box=review.box)


@router.post("/{card_id}/review", response_model=ReviewRead)
def review_word(card_id: int, payload: ReviewInput, session: DB):
    begin_write(session)
    card = get_card(session, card_id)
    previous = session.get(VocabularyReview, str(payload.request_id))
    if previous:
        if previous.card_id != card_id or normalize(previous.answer) != normalize(payload.answer):
            raise HTTPException(409, "Этот ответ уже сохранён")
        return review_read(card, previous)
    state = session.get(VocabularyProgress, card_id)
    if not state:
        raise HTTPException(409, "Сначала добавь слово на повторение")
    if state.due_on > clock.local_day():
        raise HTTPException(409, "Сегодня это слово уже повторено. Следующая дата указана в словаре.")
    correct = normalize(payload.answer) == normalize(card.term)
    state.box = min(5, state.box + 1) if correct else 0
    state.due_on = clock.local_day() + timedelta(days=INTERVALS[state.box - 1] if correct else 1)
    state.review_count += 1
    state.correct_count += int(correct)
    review = VocabularyReview(id=str(payload.request_id), card_id=card.id, answer=payload.answer,
        is_correct=correct, reviewed_at=clock.now(), due_on=state.due_on, box=state.box)
    session.add(state)
    session.add(review)
    session.commit()
    return review_read(card, review)
