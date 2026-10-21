import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    id: int
    actor_user_id: int | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    filters: dict[str, Any]
    request_id: str | None = None
    ip_address: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_record(cls, record) -> AuditLogRead:
        try:
            filters = json.loads(record.filters_json) if record.filters_json else {}
        except (TypeError, ValueError):
            filters = {}
        return cls(
            id=record.id,
            actor_user_id=record.actor_user_id,
            action=record.action,
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            filters=filters if isinstance(filters, dict) else {},
            request_id=record.request_id,
            ip_address=record.ip_address,
            created_at=record.created_at,
        )
