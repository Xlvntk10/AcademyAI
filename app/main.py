"""Academy AI API. Database preparation is an explicit, separate command."""
from fastapi import FastAPI
from app.database.db import engine
from app.routers.exercises import router
from app.routers.planner import router as planner_router
from app.routers.analytics import router as analytics_router
from app.routers.vocabulary import router as vocabulary_router
from app.routers.ielts import router as ielts_router
from app.routers.offline import router as offline_router
from app.routers.widgets import router as widgets_router


def create_app(database_engine=None):
    application = FastAPI(title="Academy AI", version="2.0.0")
    application.state.engine = database_engine if database_engine is not None else engine
    application.include_router(router)
    application.include_router(planner_router)
    application.include_router(analytics_router)
    application.include_router(vocabulary_router)
    application.include_router(ielts_router)
    application.include_router(offline_router)
    application.include_router(widgets_router)

    @application.middleware("http")
    async def private_api_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.get("/")
    def home():
        return {"message": "Academy AI: IELTS preparation", "docs": "/docs"}

    return application


app = create_app()
