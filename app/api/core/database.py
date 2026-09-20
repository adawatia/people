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
    return create_engine(settings.resolved_database_url_sync(), pool_pre_ping=True)

def get_async_engine() -> AsyncEngine:
    return create_async_engine(settings.resolved_database_url(), pool_pre_ping=True)

# Global async engine and session maker
auth_engine = get_async_engine()
async_session_maker = async_sessionmaker(auth_engine, expire_on_commit=False)

async def get_async_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        yield session

def check_database_connection() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))