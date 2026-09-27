from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def acquire_erp_upsert_lock(session: AsyncSession, entity: str, erp_id: str) -> None:
    """Serialize concurrent upserts for one ERP identity within the transaction."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"people-erp:{entity}:{erp_id}"},
    )
