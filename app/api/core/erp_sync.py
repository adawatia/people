from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def error_text(detail: object) -> str:
    """Flatten a raised error's detail into one string for a bulk failure row."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        reason = detail.get("reason") or detail.get("message") or detail.get("code")
        if reason:
            return str(reason)
    if isinstance(detail, list):
        messages = [str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail]
        if messages:
            return "; ".join(messages)
    return str(detail)


async def acquire_erp_upsert_lock(session: AsyncSession, entity: str, erp_id: str) -> None:
    """Serialize concurrent upserts for one ERP identity within the transaction."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"people-erp:{entity}:{erp_id}"},
    )


async def acquire_erp_upsert_locks(session: AsyncSession, entity: str, keys: list[str]) -> None:
    """Serialize concurrent upserts for many identities in one round trip.

    Bulk ingestion must not issue one lock query per row. The keys are sorted
    before locking so two overlapping chunks take the same advisory locks in the
    same order and cannot deadlock.
    """
    lock_keys = sorted({f"people-erp:{entity}:{key}" for key in keys})
    if not lock_keys:
        return
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(lock_key, 0)) "
            "FROM unnest(CAST(:lock_keys AS text[])) AS lock_key"
        ),
        {"lock_keys": lock_keys},
    )
