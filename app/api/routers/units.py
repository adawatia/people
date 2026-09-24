from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from core.pagination import PaginatedResponse
from core.sorting import LookupSort
from db.models import Unit, User
from schemas import UnitRead
from services.lookup_service import LookupService
from services.org_service import OrgService

router = APIRouter(prefix="/org/units", tags=["units"])


@router.get("", response_model=PaginatedResponse[UnitRead])
async def list_units(
    organization_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: LookupSort | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[UnitRead]:
    return await LookupService(session).list_page(Unit, page=page, page_size=page_size,
        search=search, sort_by=sort_by, sort_order=sort_order, filters={"organization_id": organization_id})


@router.get("/{unit_id}", response_model=UnitRead)
async def get_unit(
    unit_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UnitRead:
    service = OrgService(session)
    unit = await service.get_unit(unit_id)
    return UnitRead.model_validate(unit)
