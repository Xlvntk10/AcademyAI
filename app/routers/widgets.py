"""Versioned, read-only projection for future native widget clients."""
from fastapi import APIRouter
from sqlmodel import select
from app.database.models import LessonMeta, LessonContent, StudyTask
from app.routers.exercises import DB
from app.services import clock, planner
from app.services.analytics import dashboard
from app.services.mastery import curriculum_state

router = APIRouter(prefix="/api/widgets/v1", tags=["widgets"])


@router.get("/summary")
def summary(session: DB):
    now = clock.now()
    today = clock.local_day(now)
    prefs = planner.settings(session)
    stats = dashboard(session)
    state = curriculum_state(session)
    subjects = []
    for subject in stats["subjects"]:
        identifiers = session.exec(select(LessonMeta.lesson_id).join(LessonContent, LessonContent.lesson_id == LessonMeta.lesson_id)
                                   .where(LessonMeta.subject == subject["subject"])).all()
        subjects.append(dict(subject=subject["subject"], completed_lessons=subject["completed_lessons"],
            mastered_lessons=sum(state[i]["mastered"] for i in identifiers), available_lessons=len(identifiers),
            lesson_xp=subject["lesson_xp"], route="/#learn"))
    tasks = session.exec(select(StudyTask).where(StudyTask.scheduled_date == today,
                        StudyTask.status != "cancelled").order_by(StudyTask.created_at, StudyTask.id)).all()
    target = prefs.masters_target_date
    return dict(schema_version=1, generated_at=now, timezone=prefs.timezone, today=today,
        refresh_after_seconds=300, streak=dict(current=stats["current_streak"], longest=stats["longest_streak"], route="/#progress"),
        today_tasks=[dict(id=t.id, title=t.title, subject=t.subject, status=t.status, planned_minutes=t.planned_minutes,
                         route="/#plan") for t in tasks], subjects=subjects,
        masters_countdown=dict(target_year=2028, target_date=target,
            days_remaining=max(0, (target-today).days) if target else None,
            past_target=target < today if target else False, route="/#settings"))
