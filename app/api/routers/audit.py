from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import current_sensitive_user
from core.database import get_async_session
from core.pagination import PaginatedResponse
from core.sorting import AuditLogSort
from db.models import User
from repositories.audit_repo import AuditRepository
from schemas.audit import AuditLogRead

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=PaginatedResponse[AuditLogRead], summary="List security audit events")
async def list_audit_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    action: str | None = Query(None, max_length=100),
    entity_type: str | None = Query(None, max_length=100),
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    sort_by: AuditLogSort | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    actor: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[AuditLogRead]:
    if not actor.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Technical administrator access required")
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="from_date must not exceed to_date"
        )
    result = await AuditRepository(session).list_page(
        page=page,
        page_size=page_size,
        search=search,
        action=action,
        entity_type=entity_type,
        from_date=from_date,
        to_date=to_date,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    result["items"] = [AuditLogRead.from_record(item) for item in result["items"]]
    return PaginatedResponse[AuditLogRead](**result)
