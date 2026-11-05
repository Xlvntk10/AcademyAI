from fastapi import APIRouter, Request
from sqlalchemy import text
from app.routers.exercises import DB, progress
from app.services import clock, planner
from app.services.analytics import dashboard
from app.services.sync import plan_revision

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/snapshot")
def snapshot(request: Request, session: DB):
    # One SQLite read transaction gives the second device a consistent snapshot.
    if not session.info.get("account"):
        session.exec(text("BEGIN"))
    return {
        "protocol": 1,
        "user_id": getattr(request.state, "user", {}).get("id"),
        "generated_at": clock.now(),
        "plan_revision": plan_revision(session),
        "progress": progress(session),
        "dashboard": dashboard(session),
        "week": planner.week_read(session, clock.local_day()),
    }
