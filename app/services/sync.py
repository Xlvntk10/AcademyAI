"""Content revisions protect planner edits from stale devices."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import select
from app.database.models import StudySettings, PlanWeek, StudyTask, TaskMove


def plan_revision(session):
    if not session.info.get("account"):
        return None
    rows = {}
    for model in (StudySettings, PlanWeek, StudyTask, TaskMove):
        values = [row.model_dump(mode="json") for row in session.exec(select(model)).all()]
        rows[model.__tablename__] = sorted(values, key=lambda row: json.dumps(row, sort_keys=True))
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def begin_plan_write(session):
    session.exec(text("BEGIN IMMEDIATE"))
    if session.info.get("account"):
        expected = session.info.get("plan_revision")
        if not expected:
            raise HTTPException(428, "Сначала загрузи актуальный план")
        if expected != plan_revision(session):
            raise HTTPException(409, "План изменён на другом устройстве. Сохрани свои изменения отдельно и загрузи свежую версию.")
