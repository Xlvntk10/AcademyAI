"""Academy AI API. Database preparation is an explicit, separate command."""
from fastapi import FastAPI
from app.database.db import engine
from app.routers.exercises import router


def create_app(database_engine=None):
    application = FastAPI(title="Academy AI", version="2.0.0")
    application.state.engine = database_engine if database_engine is not None else engine
    application.include_router(router)

    @application.get("/")
    def home():
        return {"message": "Academy AI: IELTS preparation", "docs": "/docs"}

    return application


app = create_app()
