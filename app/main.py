"""Academy AI API. Database preparation is an explicit, separate command."""
from fastapi import FastAPI
from app.database.db import engine
from app.routers.exercises import router
from app.routers.planner import router as planner_router
from app.routers.analytics import router as analytics_router
from app.routers.vocabulary import router as vocabulary_router


def create_app(database_engine=None):
    application = FastAPI(title="Academy AI", version="2.0.0")
    application.state.engine = database_engine if database_engine is not None else engine
    application.include_router(router)
    application.include_router(planner_router)
    application.include_router(analytics_router)
    application.include_router(vocabulary_router)

    @application.get("/")
    def home():
        return {"message": "Academy AI: IELTS preparation", "docs": "/docs"}

    return application


app = create_app()
