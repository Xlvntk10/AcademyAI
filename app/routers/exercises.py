"""Lesson API with server grading and account-scoped storage."""
from app.database.db import begin_write
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from sqlalchemy import text
from app.database.models import Attempt, Exercise, ExerciseContent, Lesson, LessonContent, LessonRun, RunAnswer
from app.schemas import StartRun, SubmitAnswer, LessonRead, LessonDetail, ExerciseRead, RunRead, LessonStats, ProgressRead
from app.services.learning import (normalize, lesson_by_slug, exercises_for, lesson_summary,
    exercise_public, get_run, run_result, lesson_stats, grade_answer)
from app.services import clock
from app.services.mastery import curriculum_state

router = APIRouter(prefix="/api")


def get_session(request: Request):
    with Session(getattr(request.state, "engine", request.app.state.engine)) as session:
        session.info["account"] = getattr(request.state, "user", None)
        session.info["plan_revision"] = request.headers.get("if-match")
        if session.info["account"] and request.method == "GET":
            if session.get_bind().dialect.name == "postgresql":
                session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            else:
                session.exec(text("BEGIN"))
        yield session


DB = Annotated[Session, Depends(get_session)]


@router.get("/health")
def health(session: DB):
    cloud = session.get_bind().dialect.name == "postgresql"
    try:
        table = "academy_migrations.alembic_version" if cloud else "alembic_version"
        revision = session.exec(text(f"SELECT version_num FROM {table}")).scalar_one()
    except Exception as exc:
        command = "scripts.migrate_cloud" if cloud else "scripts.prepare_db"
        raise HTTPException(503, "База не подготовлена. Запустите python -m " + command) from exc
    expected = "cloud_0001" if cloud else "0009_offline_sync"
    if revision != expected:
        raise HTTPException(503, "Требуется миграция базы")
    return {"status": "ok", "schema": revision}


@router.get("/lessons", response_model=list[LessonRead])
def lessons(session: DB):
    state = curriculum_state(session)
    return [lesson_summary(session, lesson, content, state) for lesson, content in
        session.exec(select(Lesson, LessonContent).join(LessonContent).order_by(Lesson.id)).all()]


@router.get("/lessons/{slug}", response_model=LessonDetail)
def lesson_detail(slug: str, session: DB):
    lesson, content = lesson_by_slug(session, slug)
    return {**lesson_summary(session, lesson, content), "theory": content.theory,
        "exercises": [exercise_public(e, c) for e, c in exercises_for(session, lesson.id)]}


@router.get("/lessons/{slug}/exercises", response_model=list[ExerciseRead])
def lesson_exercises(slug: str, session: DB):
    lesson, _ = lesson_by_slug(session, slug)
    return [exercise_public(e, c) for e, c in exercises_for(session, lesson.id)]


@router.get("/lessons/{slug}/stats", response_model=LessonStats)
def stats(slug: str, session: DB):
    return lesson_stats(session, *lesson_by_slug(session, slug))


@router.post("/lessons/{slug}/runs", response_model=RunRead)
def start_run(slug: str, payload: StartRun, session: DB):
    # Serialize writers before reading: retries and concurrent tabs cannot create duplicate active runs.
    begin_write(session)
    lesson, content = lesson_by_slug(session, slug)
    existing = session.get(LessonRun, str(payload.request_id))
    if existing:
        if existing.lesson_id != lesson.id:
            raise HTTPException(409, "Этот идентификатор уже используется другим уроком")
        return run_result(session, existing)
    active = session.exec(select(LessonRun).where(LessonRun.lesson_id == lesson.id,
        LessonRun.completed_at.is_(None))).first()
    if active:
        return run_result(session, active)
    if not curriculum_state(session)[lesson.id]["unlocked"]:
        raise HTTPException(409, "Сначала освой предыдущие темы: не менее 80% за завершённый урок")
    run = LessonRun(id=str(payload.request_id), lesson_id=lesson.id, content_version=content.version, started_at=clock.now())
    session.add(run)
    session.commit()
    return run_result(session, run)


@router.get("/runs/{run_id}", response_model=RunRead)
def read_run(run_id: UUID, session: DB):
    return run_result(session, get_run(session, run_id))


@router.post("/runs/{run_id}/answers", response_model=RunRead)
def submit_answer(run_id: UUID, payload: SubmitAnswer, session: DB):
    begin_write(session)
    run = get_run(session, run_id)
    exercise = session.get(Exercise, payload.exercise_id)
    content = session.get(ExerciseContent, payload.exercise_id)
    if not exercise or not content or exercise.lesson_id != run.lesson_id:
        raise HTTPException(404, "Упражнение не найдено в этом уроке")
    previous = session.exec(select(RunAnswer).where(RunAnswer.run_id == run.id,
        RunAnswer.exercise_id == exercise.id)).first()
    if previous:
        attempt = session.get(Attempt, previous.attempt_id)
        if normalize(attempt.answer, content.case_sensitive) != normalize(payload.answer, content.case_sensitive):
            raise HTTPException(409, "Ответ уже сохранён. Начните новое прохождение после завершения урока.")
        return run_result(session, run)
    if run.completed_at:
        raise HTTPException(409, "Прохождение уже завершено")
    lesson_content = session.get(LessonContent, run.lesson_id)
    if lesson_content.version != run.content_version:
        raise HTTPException(409, "Версия урока изменилась")
    correct = grade_answer(exercise, content, payload.answer)
    attempt = Attempt(exercise_id=exercise.id, answer=payload.answer, is_correct=correct,
        earned_points=exercise.points if correct else 0, created_at=clock.now())
    session.add(attempt)
    session.flush()
    session.add(RunAnswer(run_id=run.id, exercise_id=exercise.id, attempt_id=attempt.id))
    session.flush()
    count = len(session.exec(select(RunAnswer).where(RunAnswer.run_id == run.id)).all())
    if count == len(exercises_for(session, run.lesson_id)):
        run.completed_at = clock.now()
        session.add(run)
    session.commit()
    return run_result(session, run)


@router.get("/progress", response_model=ProgressRead)
def progress(session: DB):
    from app.services.analytics import dashboard
    items = [lesson_stats(session, lesson, content) for lesson, content in
        session.exec(select(Lesson, LessonContent).join(LessonContent).order_by(Lesson.id)).all()]
    return dict(completed_lessons=sum(i["completed_runs"] > 0 for i in items),
        completed_runs=sum(i["completed_runs"] for i in items), total_xp=dashboard(session)["total_xp"], lessons=items)
