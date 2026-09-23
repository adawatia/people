"""Small append-only audit helper for privileged read access."""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog, User


def add_audit_event(
    session: AsyncSession,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    filters: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Stage an audit row inside the caller's transaction.

    Use this from services that already own a transaction, so the audit row
    commits atomically with the change. ``actor`` may be ``None`` for
    machine-to-machine paths such as the ERP integration.
    """
    session.add(
        AuditLog(
            actor_user_id=actor.id if actor is not None else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            filters_json=json.dumps(filters or {}, sort_keys=True, default=str),
            request_id=request_id,
            ip_address=ip_address,
        )
    )


async def record_audit_event(
    session: AsyncSession,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    filters: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Stage an audit row and commit it (for read-style audit events)."""
    add_audit_event(
        session,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        filters=filters,
        request_id=request_id,
        ip_address=ip_address,
    )
    await session.commit()
