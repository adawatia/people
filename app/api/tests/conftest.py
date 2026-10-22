"""Automated ephemeral test database lifecycle.

At session start:
1. Connects to the PostgreSQL maintenance database (`postgres` or `template1`).
2. Cleans up any orphan `people_test_*` databases from previously interrupted runs.
3. Creates a fresh isolated database `people_test_<uuid>`.
4. Initializes all tables and baseline seeds.
5. Injects `DATABASE_URL` so all application code and test sessions run in 100% isolation.

At session finish:
1. Disposes all connection pools.
2. Terminates remaining connections and drops the test database cleanly.
"""

from __future__ import annotations

import asyncio
import os
import selectors
import sys
import uuid

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

# Every test runs on its own event loop, so a pooled asyncpg/psycopg connection would
# outlive it and fail on reuse. This must be set before the application imports
# its settings, which is why it lives at module import rather than in a fixture.
os.environ.setdefault("DB_DISABLE_POOL", "true")

_TEST_DB_NAME: str | None = None
_MAINTENANCE_DB: str | None = None
_BASE_PARAMS: dict[str, str | int] | None = None


def _get_maintenance_connection(user: str, password: str, host: str, port: int) -> tuple[psycopg.Connection, str]:
    """Connect to the administrative database (trying 'postgres' then 'template1')."""
    errors: list[str] = []
    for maint_db in ("postgres", "template1"):
        try:
            conn = psycopg.connect(f"postgresql://{user}:{password}@{host}:{port}/{maint_db}", autocommit=True)
            return conn, maint_db
        except Exception as exc:
            errors.append(f"{maint_db}: {exc}")
    raise pytest.UsageError(
        f"Could not connect to PostgreSQL maintenance database on {host}:{port}. Attempted: {'; '.join(errors)}"
    )


def _run_async(coro):
    """Run an async coroutine across platforms (using SelectorEventLoop on Windows)."""
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    return asyncio.run(coro)


def pytest_sessionstart(session: pytest.Session) -> None:
    global _TEST_DB_NAME, _MAINTENANCE_DB, _BASE_PARAMS

    manual_db = os.environ.get("PYTEST_MANUAL_DB", "").strip() in ("1", "true", "yes")
    if manual_db:
        return

    from core.settings import get_settings

    settings = get_settings()

    base_url_str = settings.resolved_database_url_sync()
    parsed = make_url(base_url_str)

    user = parsed.username or "hrms-user"
    password = parsed.password or ""
    host = parsed.host or "localhost"
    port = parsed.port or 5432

    _BASE_PARAMS = {"user": user, "password": password, "host": host, "port": port}

    reuse_db = os.environ.get("PYTEST_REUSE_DB", "").strip() in ("1", "true", "yes")
    if reuse_db:
        _TEST_DB_NAME = "people_test_reusable"
    else:
        _TEST_DB_NAME = f"people_test_{uuid.uuid4().hex[:8]}"

    try:
        conn, _MAINTENANCE_DB = _get_maintenance_connection(user, password, host, port)
        with conn:
            # Clean up orphan databases from previous aborted runs
            if not reuse_db:
                orphans = conn.execute(
                    "SELECT datname FROM pg_database WHERE datname LIKE %s AND datname <> %s",
                    ("people_test_%", _TEST_DB_NAME),
                ).fetchall()
                for (orphan,) in orphans:
                    try:
                        conn.execute(
                            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                            "WHERE datname = %s AND pid <> pg_backend_pid()",
                            (orphan,),
                        )
                        conn.execute(f'DROP DATABASE IF EXISTS "{orphan}" WITH (FORCE)')
                    except Exception:
                        pass

            # Create the test database if it doesn't already exist
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (_TEST_DB_NAME,),
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
    except Exception as exc:
        raise pytest.UsageError(f"Could not initialize test database on PostgreSQL: {exc}") from exc

    # Point the application and test engine to the test database
    test_db_url_sync = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{_TEST_DB_NAME}"
    os.environ["DATABASE_URL"] = test_db_url_sync

    # Clear cached settings so get_settings() re-reads the new DATABASE_URL
    get_settings.cache_clear()

    # Initialize all database tables using synchronous engine
    from db.models import Base

    sync_engine = create_engine(test_db_url_sync)
    try:
        Base.metadata.create_all(sync_engine)
    finally:
        sync_engine.dispose()

    # Re-initialize the core database engine to ensure it binds to the new test DB
    import core.database

    core.database.settings = get_settings()
    core.database.get_engine.cache_clear()
    core.database.auth_engine = core.database.get_async_engine()
    core.database.async_session_maker = core.database.async_sessionmaker(
        core.database.auth_engine, expire_on_commit=False
    )

    # Baseline seed data (Organization singleton + Super Admin)
    from db.seed import ensure_seed_data

    _run_async(ensure_seed_data())


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _TEST_DB_NAME or not _BASE_PARAMS or not _MAINTENANCE_DB:
        return

    reuse_db = os.environ.get("PYTEST_REUSE_DB", "").strip() in ("1", "true", "yes")
    if reuse_db:
        return

    # Dispose application engines
    try:
        import core.database

        core.database.get_engine().dispose()
    except Exception:
        pass

    try:
        import core.database

        _run_async(core.database.auth_engine.dispose())
    except Exception:
        pass

    # Terminate connections and drop the database
    try:
        conn = psycopg.connect(
            f"postgresql://{_BASE_PARAMS['user']}:{_BASE_PARAMS['password']}@"
            f"{_BASE_PARAMS['host']}:{_BASE_PARAMS['port']}/{_MAINTENANCE_DB}",
            autocommit=True,
        )
        with conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (_TEST_DB_NAME,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
    except Exception:
        pass
