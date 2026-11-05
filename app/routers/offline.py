"""One atomic, idempotent receipt per offline attempt. Scores stay server-owned."""
from app.database.db import begin_write
import hashlib
import json
from datetime import timedelta
from fastapi import APIRouter, HTTPException
from app.database.models import Attempt, LessonRun, RunAnswer, OfflineReceipt, SyncIdentity
from app.offline_schemas import OfflineBundle, OfflineSubmission, OfflineAcknowledgement
from app.routers.exercises import DB
from app.services import clock
from app.services.learning import lesson_by_slug, lesson_summary, exercises_for, exercise_public, grade_answer, run_result, utc
from app.services.mastery import curriculum_state

router = APIRouter(prefix="/api/offline", tags=["offline"])


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def content_hash(lesson, content, exercises):
    # Include grading rules in the revision fingerprint without disclosing them.
    return digest({"lesson": lesson.model_dump(), "content": content.model_dump(),
                   "exercises": [(e.model_dump(), c.model_dump()) for e, c in exercises]})


@router.get("/lessons/{slug}", response_model=OfflineBundle)
def download(slug: str, session: DB):
    lesson, content = lesson_by_slug(session, slug)
    exercises = exercises_for(session, lesson.id)
    return dict(protocol=1, server_id=session.get(SyncIdentity, 1).server_id,
        content_hash=content_hash(lesson, content, exercises), downloaded_at=clock.now(),
        lesson={**lesson_summary(session, lesson, content), "theory": content.theory,
                "exercises": [exercise_public(e, c) for e, c in exercises]})


@router.post("/attempts", response_model=OfflineAcknowledgement)
def sync_attempt(payload: OfflineSubmission, session: DB):
    begin_write(session)
    if str(payload.server_id) != session.get(SyncIdentity, 1).server_id:
        raise HTTPException(409, "Подключена другая база Academy AI. Вернись к исходному серверу.")
    serialized = payload.model_dump(mode="json")
    serialized["answers"] = sorted(serialized["answers"], key=lambda a: a["exercise_id"])
    fingerprint = digest(serialized)
    identifier = str(payload.attempt_id)
    receipt = session.get(OfflineReceipt, identifier)
    if receipt:
        if receipt.payload_hash != fingerprint:
            raise HTTPException(409, "Эта попытка уже принята с другими ответами. Локальная копия сохранена.")
        return dict(attempt_id=identifier, received_at=utc(receipt.received_at), result=receipt.result)
    if session.get(LessonRun, identifier):
        raise HTTPException(409, "Идентификатор уже занят другим прохождением")
    lesson, content = lesson_by_slug(session, payload.lesson_slug)
    exercises = exercises_for(session, lesson.id)
    if content.version != payload.content_version or content_hash(lesson, content, exercises) != payload.content_hash:
        raise HTTPException(409, "Урок обновлён. Сохрани ответы и скачай новую версию для повторного прохождения.")
    if not curriculum_state(session)[lesson.id]["unlocked"]:
        raise HTTPException(409, "Сначала синхронизируй освоенные предыдущие темы, затем повтори отправку")
    if {a.exercise_id for a in payload.answers} != {e.id for e, _ in exercises}:
        raise HTTPException(422, "Нужен один ответ на каждое упражнение этой версии урока")
    received = clock.now()
    if payload.completed_at > received + timedelta(minutes=5):
        raise HTTPException(422, "Проверь часы устройства. Время попытки находится в будущем.")
    answers = {a.exercise_id: a.answer for a in payload.answers}
    graded = [(e, answers[e.id], grade_answer(e, c, answers[e.id])) for e, c in exercises]
    # Client timestamps are retained as metadata. Trusted activity dates use server time.
    run = LessonRun(id=identifier, lesson_id=lesson.id, content_version=content.version,
                    started_at=received, completed_at=received)
    session.add(run)
    session.flush()
    for exercise, answer, correct in graded:
        attempt = Attempt(exercise_id=exercise.id, answer=answer, is_correct=correct,
                          earned_points=exercise.points if correct else 0, created_at=received)
        session.add(attempt)
        session.flush()
        session.add(RunAnswer(run_id=identifier, exercise_id=exercise.id, attempt_id=attempt.id))
    session.flush()
    result = run_result(session, run)
    # Store the acknowledgement itself so a lost HTTP response can be replayed exactly.
    acknowledgement = OfflineAcknowledgement(attempt_id=identifier, received_at=received, result=result)
    session.add(OfflineReceipt(id=identifier, payload_hash=fingerprint, client_started_at=payload.started_at,
        client_completed_at=payload.completed_at, received_at=received, result=acknowledgement.model_dump(mode="json")["result"]))
    session.commit()
    return acknowledgement
