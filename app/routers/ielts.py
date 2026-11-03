from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlmodel import select
from app.database.models import IeltsRun, IeltsTest
from app.ielts_schemas import DraftInput, IeltsRunRead
from app.schemas import StartRun
from app.routers.exercises import DB
from app.services import clock, ielts

router = APIRouter(prefix="/api/ielts", tags=["ielts"])


@router.get("/tests")
def tests(session: DB):
    return [{key: getattr(t, key) for key in ("id", "section", "title", "instructions", "duration_seconds")}
        for t in session.exec(select(IeltsTest).order_by(IeltsTest.id)).all()]


@router.get("/tests/{test_id}")
def read_test(test_id: str, session: DB):
    return ielts.test_read(ielts.get_test(session, test_id))


@router.post("/tests/{test_id}/runs", response_model=IeltsRunRead)
def start(test_id: str, payload: StartRun, session: DB):
    session.exec(text("BEGIN IMMEDIATE"))
    ielts.get_test(session, test_id)
    existing = session.get(IeltsRun, str(payload.request_id))
    if existing:
        if existing.test_id != test_id:
            raise HTTPException(409, "Идентификатор занят другой тренировкой")
        return ielts.run_read(session, existing)
    run = IeltsRun(id=str(payload.request_id), test_id=test_id, started_at=clock.now(), updated_at=clock.now())
    session.add(run)
    session.commit()
    return ielts.run_read(session, run)


@router.get("/history", response_model=list[IeltsRunRead])
def history(session: DB, limit: int = Query(default=50, ge=1, le=200)):
    return [ielts.run_read(session, r) for r in session.exec(select(IeltsRun).order_by(IeltsRun.started_at.desc()).limit(limit)).all()]


@router.get("/runs/{run_id}", response_model=IeltsRunRead)
def read_run(run_id: UUID, session: DB):
    return ielts.run_read(session, ielts.get_run(session, run_id))


@router.post("/runs/{run_id}/save", response_model=IeltsRunRead)
def save(run_id: UUID, payload: DraftInput, session: DB):
    session.exec(text("BEGIN IMMEDIATE"))
    return ielts.run_read(session, ielts.save(session, ielts.get_run(session, run_id), payload))


@router.post("/runs/{run_id}/submit", response_model=IeltsRunRead)
def submit(run_id: UUID, payload: DraftInput, session: DB):
    session.exec(text("BEGIN IMMEDIATE"))
    return ielts.run_read(session, ielts.save(session, ielts.get_run(session, run_id), payload, submit=True))
