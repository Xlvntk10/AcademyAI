"""Academy AI API. Database preparation is an explicit, separate command."""
import os
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError
from app.cloud_accounts import CloudAccounts
from app.accounts import AccountConfig, Accounts, COOKIE
from app.routers.accounts import router as accounts_router
from app.routers.sync import router as sync_router
from app.database.db import engine
from app.routers.exercises import router
from app.routers.planner import router as planner_router
from app.routers.analytics import router as analytics_router
from app.routers.vocabulary import router as vocabulary_router
from app.routers.ielts import router as ielts_router
from app.routers.offline import router as offline_router
from app.routers.widgets import router as widgets_router


def create_app(database_engine=None, accounts=None):
    application = FastAPI(title="Academy AI", version="2.0.0")
    application.state.engine = database_engine if database_engine is not None else engine
    cloud = application.state.engine.dialect.name == "postgresql"
    if os.environ.get("ACADEMY_ENV") == "production":
        if not cloud:
            raise RuntimeError("Production requires PostgreSQL persistent storage")
        if application.state.engine.url.query.get("sslmode") != "verify-full":
            raise RuntimeError("Production PostgreSQL requires TLS sslmode=verify-full")
    config = AccountConfig.from_environment(cloud=cloud) if accounts is None else None
    if cloud and accounts is None and config is None:
        raise RuntimeError("PostgreSQL requires Supabase account mode")
    manager = accounts
    if manager is None and config:
        manager = CloudAccounts(config, application.state.engine) if cloud else Accounts(config)
    if os.environ.get("ACADEMY_ENV") == "production" and (not manager or not manager.config.secure):
        raise RuntimeError("Production accounts require an HTTPS public origin")
    application.state.accounts = manager
    application.include_router(accounts_router)
    application.include_router(sync_router)
    application.include_router(router)
    application.include_router(planner_router)
    application.include_router(analytics_router)
    application.include_router(vocabulary_router)
    application.include_router(ielts_router)
    application.include_router(offline_router)
    application.include_router(widgets_router)

    @application.middleware("http")
    async def private_api_responses(request, call_next):
        manager = application.state.accounts
        tenant_engine = None
        try:
            if manager and request.url.path.startswith("/api/"):
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    if request.headers.get("origin") != manager.config.origin or request.headers.get("x-academy-request") != "1":
                        raise HTTPException(403, "Запрос должен исходить из Academy AI")
                if not request.url.path.startswith("/api/auth/") and request.url.path != "/api/health":
                    user = await run_in_threadpool(manager.resolve, request.cookies.get(COOKIE))
                    if request.headers.get("x-academy-account") != user["id"]:
                        raise HTTPException(409, "Аккаунт в другой вкладке изменился. Открой приложение заново.")
                    request.state.user = user
                    tenant_engine = await run_in_threadpool(manager.tenant_engine, user["id"])
                    request.state.engine = tenant_engine
            response = await call_next(request)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        except OperationalError:
            response = JSONResponse({"detail": "База временно недоступна. Сохранённые на устройстве ответы можно отправить позже."}, status_code=503)
        finally:
            if tenant_engine is not None and tenant_engine is not application.state.engine:
                tenant_engine.dispose()
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["CDN-Cache-Control"] = "no-store"
            response.headers["Surrogate-Control"] = "no-store"
            vary = [part.strip() for part in response.headers.get("Vary", "").split(",") if part.strip()]
            for name in ("Cookie", "Origin", "X-Academy-Account"):
                if name.lower() not in {part.lower() for part in vary}:
                    vary.append(name)
            response.headers["Vary"] = ", ".join(vary)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    if os.environ.get("ACADEMY_SERVE_FRONTEND") == "1":
        from app.web import mount_frontend
        mount_frontend(application)
    else:
        @application.get("/")
        def home():
            return {"message": "Academy AI: IELTS preparation", "docs": "/docs"}

    if manager:
        application.add_middleware(CORSMiddleware, allow_origins=[manager.config.origin],
            allow_credentials=True, allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Academy-Request", "X-Academy-Account", "If-Match"])
    return application


app = create_app()
