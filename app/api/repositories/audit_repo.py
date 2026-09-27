from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import ordered, paginate
from db.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        action: str | None,
        entity_type: str | None,
        from_date: datetime | None,
        to_date: datetime | None,
        sort_by: str | None,
        sort_order: str,
    ) -> dict:
        query = select(AuditLog)
        if search and search.strip():
            value = search.strip()
            query = query.where(
                or_(
                    AuditLog.action.icontains(value, autoescape=True),
                    AuditLog.entity_type.icontains(value, autoescape=True),
                    AuditLog.entity_id.icontains(value, autoescape=True),
                    AuditLog.request_id.icontains(value, autoescape=True),
                )
            )
        if action:
            query = query.where(AuditLog.action == action.strip())
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type.strip())
        if from_date:
            query = query.where(AuditLog.created_at >= from_date)
        if to_date:
            query = query.where(AuditLog.created_at <= to_date)
        query = ordered(
            query,
            {
                "created_at": AuditLog.created_at,
                "action": AuditLog.action,
                "entity_type": AuditLog.entity_type,
                "id": AuditLog.id,
            },
            sort_by,
            sort_order,
            "created_at",
            AuditLog.id,
        )
        return await paginate(self.session, query, page, page_size)
