from datetime import date
from uuid import UUID
from fastapi import APIRouter, Query
from sqlalchemy import text
from sqlmodel import select
from app.database.models import StudyTask
from app.planner_schemas import SettingsInput, SettingsRead, GenerateWeek, CompleteTask, RescheduleTask, WeekRead, TaskRead, ReminderInput
from app.routers.exercises import DB
from app.services import planner, clock

router = APIRouter(prefix="/api/planner", tags=["planner"])


@router.get("/settings", response_model=SettingsRead)
def read_settings(session: DB):
    return {**planner.settings(session).model_dump(exclude={"id"}), "english_percent": 65}


@router.post("/settings", response_model=SettingsRead)
def save_settings(payload: SettingsInput, session: DB):
    session.exec(text("BEGIN IMMEDIATE"))
    settings = planner.settings(session)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return {**settings.model_dump(exclude={"id"}), "english_percent": 65}


@router.get("/week", response_model=WeekRead)
def week(session: DB, start: date | None = None):
    return planner.week_read(session, start or clock.local_day())


@router.post("/reminder", response_model=SettingsRead)
def save_reminder(payload: ReminderInput, session: DB):
    session.exec(text("BEGIN IMMEDIATE"))
    prefs = planner.settings(session)
    prefs.reminder_enabled = payload.reminder_enabled
    prefs.reminder_time = payload.reminder_time
    session.add(prefs)
    session.commit()
    session.refresh(prefs)
    return {**prefs.model_dump(exclude={"id"}), "english_percent": 65}


@router.post("/generate", response_model=WeekRead)
def generate(payload: GenerateWeek, session: DB):
    session.exec(text("BEGIN IMMEDIATE"))
    planner.generate(session, payload.week_start, payload.replace_pending)
    session.commit()
    return planner.week_read(session, payload.week_start)


@router.post("/tasks/{task_id}/complete", response_model=TaskRead)
def complete(task_id: UUID, payload: CompleteTask, session: DB):
    session.exec(text("BEGIN IMMEDIATE"))
    task = planner.get_task(session, task_id)
    planner.complete(session, task, payload.actual_minutes)
    session.commit()
    return planner.task_read(session, task)


@router.post("/tasks/{task_id}/reschedule", response_model=TaskRead)
def reschedule(task_id: UUID, payload: RescheduleTask, session: DB):
    session.exec(text("BEGIN IMMEDIATE"))
    task = planner.get_task(session, task_id)
    planner.reschedule(session, task, payload.scheduled_date)
    session.commit()
    return planner.task_read(session, task)


@router.get("/history", response_model=list[TaskRead])
def history(session: DB, limit: int = Query(default=50, ge=1, le=200)):
    tasks = session.exec(select(StudyTask).where(StudyTask.status == "completed")
        .order_by(StudyTask.completed_at.desc()).limit(limit)).all()
    return [planner.task_read(session, task) for task in tasks]
