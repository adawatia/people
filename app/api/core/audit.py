"""Small append-only audit helper for privileged read access."""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog, User


async def record_audit_event(
    session: AsyncSession,
    *,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    filters: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            filters_json=json.dumps(filters or {}, sort_keys=True, default=str),
            request_id=request_id,
            ip_address=ip_address,
        )
    )
    await session.commit()
