"""
core/database.py — Database engine and session management.

The application talks to PostgreSQL through SQLAlchemy's asyncio layer.
A single global engine is created at import time and shared by every
request; individual sessions are opened per-request via the
`get_async_session` FastAPI dependency and closed automatically.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.settings import get_settings

settings = get_settings()


def get_engine() -> Engine:
    """Build a synchronous engine (used by health checks and Alembic)."""
    # pool_pre_ping issues a lightweight liveness check before reusing a
    # pooled connection, so stale connections (e.g. after a DB restart)
    # fail transparently instead of raising on the first query.
    return create_engine(settings.resolved_database_url_sync(), pool_pre_ping=True)


def get_async_engine() -> AsyncEngine:
    """Build the async engine used by all request-scoped work."""
    return create_async_engine(settings.resolved_database_url(), pool_pre_ping=True)


# Global async engine and session maker.
#
# `expire_on_commit=False` keeps ORM objects usable after `session.commit()`
# — without it every attribute access after a commit would trigger a fresh
# SELECT, which is wasteful in request handlers that commit then return data.
auth_engine = get_async_engine()
async_session_maker = async_sessionmaker(auth_engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed on exit."""
    async with async_session_maker() as session:
        yield session


def check_database_connection() -> None:
    """Raise if the database is unreachable; used by the /health endpoints."""
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
