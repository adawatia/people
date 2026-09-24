from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from core.pagination import PaginatedResponse
from core.sorting import LookupSort
from db.models import HolidayList, User
from schemas.holidays import HolidayListRead
from services.holiday_service import HolidayService
from services.lookup_service import LookupService

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("/lists", response_model=PaginatedResponse[HolidayListRead])
async def list_holiday_lists(
    unit_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: LookupSort | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[HolidayListRead]:
    return await LookupService(session).list_page(HolidayList, page=page, page_size=page_size,
        search=search, sort_by=sort_by, sort_order=sort_order, filters={"unit_id": unit_id})


@router.get("/lists/{list_id}", response_model=HolidayListRead)
async def get_holiday_list(
    list_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> HolidayListRead:
    service = HolidayService(session)
    hl = await service.get_holiday_list(list_id)
    return HolidayListRead.model_validate(hl)
