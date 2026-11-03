from fastapi import APIRouter
from app.analytics_schemas import Dashboard
from app.routers.exercises import DB
from app.services.analytics import dashboard

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/dashboard", response_model=Dashboard)
def read_dashboard(session: DB):
    return dashboard(session)
