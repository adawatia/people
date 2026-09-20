import asyncio
import os
import time
import warnings
import sys
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# Suppress known non-blocking deprecation warnings from third-party dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*iscoroutinefunction.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*on_event is deprecated.*")
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, Request
from core.auth import (
    auth_backend,
    fastapi_users,
    limiter,
    setup_rate_limits,
)
from schemas import UserRead, UserUpdate
from routers import auth_sessions
from core.database import check_database_connection
from core.logging import setup_logging
from core.settings import get_settings

APP_START_TIME = time.monotonic()

settings = get_settings()
logger = setup_logging(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    from db.seed import create_db_and_tables, ensure_seed_data
    from utils.notifications_cleanup import notification_cleanup_loop

    logger.info("Starting HRMS API")
    await create_db_and_tables()
    await ensure_seed_data()
    
    # Start the background task for cleaning up notifications
    cleanup_task = asyncio.create_task(notification_cleanup_loop())
    
    yield
    
    logger.info("Shutting down HRMS API")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="HRMS API",
    version="0.1.0",
    description="Human Resource Management System API: users, roles, and notifications foundation.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "auth", "description": "Authentication and token management."},
        {"name": "users", "description": "User profile management and account administration."},
        {"name": "rbac", "description": "Dynamic scoped role assignments."},
        {"name": "roles", "description": "Role definitions and permission metadata."},
        {"name": "dashboard", "description": "Dynamic dashboard widget visibility."},
        {"name": "notifications", "description": "In-app notifications."},
    ],
)

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8081,http://127.0.0.1:8081,http://localhost:3000,http://127.0.0.1:3000,http://localhost:19006,http://127.0.0.1:19006",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.0\.2\.2|192\.168\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_rate_limits(app)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    logger.info(
        "request_started",
        extra={
            "event": "request_started",
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        },
    )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={
                "event": "request_failed",
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
        raise

    process_time_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request_completed",
        extra={
            "event": "request_completed",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": process_time_ms,
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        },
    )
    return response


from routers import (
    auth_invitation,
    dashboard,
    notifications,
    roles,
    users,
    org,
    designations,
    employees,
    shifts,
    attendance,
    leaves,
    overtime,
    holidays,
    work_arrangements,
    reports,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(users.router)
api_router.include_router(notifications.router)
api_router.include_router(roles.router)
api_router.include_router(auth_invitation.router)
api_router.include_router(auth_sessions.router)
api_router.include_router(dashboard.router)
api_router.include_router(org.router)
api_router.include_router(designations.router)
api_router.include_router(employees.router)
api_router.include_router(shifts.router)
api_router.include_router(holidays.router)
api_router.include_router(attendance.router)
api_router.include_router(leaves.router)
api_router.include_router(overtime.router)
api_router.include_router(work_arrangements.router)
api_router.include_router(reports.router)

api_router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

api_router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

app.include_router(api_router)

@app.get("/")
def root() -> dict[str, str]:
    return {"message": "HRMS API"}


@app.get("/health")
@limiter.limit("10/minute")
def health(request: Request) -> dict[str, object]:
    started = time.perf_counter()
    db_status = "unknown"
    db_detail = "not checked"
    try:
        check_database_connection()
        db_status = "connected"
        db_detail = "database reachable"
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        db_status = "disconnected"
        db_detail = str(exc)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    uptime_seconds = round(time.monotonic() - APP_START_TIME, 3)

    status_code = "ok" if db_status == "connected" else "degraded"
    return {
        "status": status_code,
        "service": "hrms-api",
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_seconds": uptime_seconds,
        "response_time_ms": elapsed_ms,
        "database": {
            "status": db_status,
            "detail": db_detail,
        },
    }



@app.get("/db-health")
def db_health() -> dict[str, str]:
    try:
        check_database_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"database unavailable: {exc}"
        ) from exc

    return {"database": "connected"}


def main() -> None:
    """Local entrypoint: `python main.py`. Mirrors `fastapi dev` defaults.

    Reload is scoped so runtime artefacts (logs, caches, venv) never trigger
    the watcher — the root cause of the previous infinite-reload loop.
    """

    import uvicorn

    app_settings = get_settings()
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level=str(app_settings.log_level or "info").lower(),
        reload_dirs=["."],
        reload_excludes=["logs/*", "*.log*", "__pycache__/*", ".venv/*", ".pytest_cache/*"],
    )


if __name__ == "__main__":
    main()
