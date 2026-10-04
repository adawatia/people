import asyncio
import os
import sys
import time
import uuid
import warnings
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# Suppress known non-blocking deprecation warnings from third-party dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*iscoroutinefunction.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*on_event is deprecated.*")
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi

from core.auth import (
    limiter,
    setup_rate_limits,
)
from core.database import auth_engine, check_database_connection, get_engine
from core.logging import setup_logging
from core.settings import get_settings
from routers import auth_mfa, auth_sessions

APP_START_TIME = time.monotonic()

settings = get_settings()
settings.validate_runtime_secrets()
logger = setup_logging(settings)
# Non-fatal hardening reminders (per-worker throttling, MFA disabled, ...) so an
# operator learns about a weakened posture from the logs rather than an incident.
for _warning in settings.security_warnings():
    logger.warning("security configuration", extra={"event": "security_config_warning", "detail": _warning})


@asynccontextmanager
async def lifespan(_: FastAPI):
    from db.seed import create_db_and_tables, ensure_seed_data
    from utils.notifications_cleanup import notification_cleanup_loop

    logger.info("Starting HRMS API")
    # Schema changes are applied by Alembic in the release process.  ``create_all``
    # remains a development convenience only; it cannot safely evolve a live DB.
    is_development = settings.environment.lower() in {"development", "dev", "test"}
    if is_development:
        await create_db_and_tables()
    # A production release must run Alembic first. Seeding is opt-in there so
    # an API worker cannot unexpectedly create a privileged account.
    if is_development or settings.bootstrap_seed_data:
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
    await auth_engine.dispose()
    # The sync health-check pool is lazy; avoid creating it merely to close it.
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="HRMS API",
    version="0.1.0",
    description="People HRMS API. ERP is the source of truth for employee and organization master data.",
    docs_url="/docs" if settings.is_development or settings.expose_api_docs else None,
    redoc_url="/redoc" if settings.is_development or settings.expose_api_docs else None,
    openapi_url="/openapi.json" if settings.is_development or settings.expose_api_docs else None,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "auth-employee", "description": "Regular employee login using Indian mobile number and password."},
        {"name": "auth-super-admin", "description": "Technical Super Admin login using username and password only."},
        {"name": "auth-account", "description": "Authenticated account password and username management."},
        {
            "name": "auth-session",
            "description": "Short-lived access tokens, rotating refresh sessions and signed-in devices.",
        },
        {"name": "auth-hr", "description": "HR Admin temporary password operations for employee accounts."},
        {
            "name": "account",
            "description": "The authenticated account profile and permissions. Employee provisioning is ERP-only.",
        },
        {
            "name": "employees",
            "description": "Read and manage employee operational records. Creation and identity provisioning are ERP-only.",
        },
        {"name": "erp-employees", "description": "ERP-only employee and linked-user provisioning and synchronization."},
        {"name": "erp-organization", "description": "ERP-only updates for the single organization record."},
        {"name": "erp-units", "description": "ERP-only unit upserts and retirement."},
        {"name": "erp-departments", "description": "ERP-only department upserts and retirement."},
        {
            "name": "erp-designations",
            "description": "ERP-only designation upserts and retirement.",
        },
        {
            "name": "erp-attendance",
            "description": "ERP-only attendance punches, records, corrections, and reconciliation.",
        },
        {"name": "erp-shifts", "description": "ERP-only shifts and employee shift assignments."},
        {"name": "erp-holidays", "description": "ERP-only organization-wide holiday synchronization."},
        {"name": "erp-overtime", "description": "ERP-only overtime record synchronization."},
        {"name": "erp-leaves", "description": "ERP leave status change feed and acknowledgements."},
        {"name": "dashboard", "description": "Operational and technical administration dashboard metrics."},
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
    allow_origin_regex=(
        r"^https?://(localhost|127\.0\.0\.1|10\.0\.2\.2|192\.168\.\d+\.\d+)(:\d+)?$"
        if settings.is_development
        else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_rate_limits(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    # One correlation id per request, reused by the security audit so a support
    # ticket can be tied back to the exact login/refresh/revocation it describes.
    # An id supplied by the caller (a gateway, or the BFF) is preserved.
    correlation_id = request.headers.get("x-request-id", "").strip()[:100] or uuid.uuid4().hex
    request.state.request_id = correlation_id
    common = {
        "method": request.method,
        "path": request.url.path,
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": correlation_id,
    }
    logger.info("request_started", extra={"event": "request_started", **common})

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"event": "request_failed", **common})
        raise

    response.headers["X-Request-ID"] = correlation_id
    logger.info(
        "request_completed",
        extra={
            "event": "request_completed",
            **common,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    )
    return response


from routers import (
    attendance,
    audit,
    auth_login,
    dashboard,
    designations,
    employees,
    erp_attendance,
    erp_employees,
    erp_holidays,
    erp_leaves,
    erp_master_data,
    erp_overtime,
    erp_shifts,
    holidays,
    leaves,
    notifications,
    org,
    overtime,
    reports,
    shifts,
    users,
    work_arrangements,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(audit.router)
api_router.include_router(users.router)
api_router.include_router(notifications.router)
api_router.include_router(auth_login.router)
api_router.include_router(auth_login.erp_router)
api_router.include_router(auth_mfa.router)
api_router.include_router(auth_sessions.router)
api_router.include_router(dashboard.router)
api_router.include_router(org.router)
api_router.include_router(designations.router)
api_router.include_router(employees.router)
api_router.include_router(shifts.router)
api_router.include_router(holidays.router)
api_router.include_router(attendance.router)
api_router.include_router(erp_attendance.router)
api_router.include_router(erp_shifts.router)
api_router.include_router(erp_leaves.router)
api_router.include_router(erp_holidays.router)
api_router.include_router(erp_overtime.router)
api_router.include_router(erp_employees.router)
api_router.include_router(erp_master_data.router)
api_router.include_router(leaves.router)
api_router.include_router(overtime.router)
api_router.include_router(work_arrangements.router)
api_router.include_router(reports.router)

app.include_router(api_router)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title, version=app.version, description=app.description, routes=app.routes, tags=app.openapi_tags
    )
    schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes["SuperAdminOAuth2"] = {
        "type": "oauth2",
        "flows": {"password": {"scopes": {}, "tokenUrl": "/api/v1/auth/super-admin/login"}},
        "description": "Super Admin username/password flow. Use the returned access token as Bearer authentication.",
    }
    schemes["ErpHmac"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-ERP-Signature",
        "description": (
            "HMAC-SHA256 over METHOD, path with query, X-ERP-Timestamp, X-ERP-Nonce, and the SHA-256 body hash, "
            "joined by newlines. X-ERP-Client-ID, X-ERP-Timestamp, X-ERP-Nonce, and X-ERP-Signature are all required."
        ),
    }
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            security = operation.get("security", [])
            if any("OAuth2PasswordBearer" in item for item in security):
                operation["security"] = [{"OAuth2PasswordBearer": []}, {"SuperAdminOAuth2": []}]
    for path, path_item in schema.get("paths", {}).items():
        if not path.startswith("/api/v1/integrations/erp"):
            continue
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation["security"] = [{"ErpHmac": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


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
        logger.error("health database check failed", exc_info=exc)
        db_detail = "database unavailable"

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
        logger.error("database health check failed", exc_info=exc)
        raise HTTPException(status_code=503, detail="database unavailable") from exc

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
