from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas.holidays import (
    HolidayCreate,
    HolidayListCreate,
    HolidayListRead,
    HolidayRead,
)
from services.holiday_service import HolidayService

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("/lists", response_model=list[HolidayListRead])
async def list_holiday_lists(
    unit_id: int | None = Query(None),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[HolidayListRead]:
    service = HolidayService(session)
    return await service.list_holiday_lists(unit_id=unit_id)


@router.get("/lists/{list_id}", response_model=HolidayListRead)
async def get_holiday_list(
    list_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> HolidayListRead:
    service = HolidayService(session)
    hl = await service.get_holiday_list(list_id)
    return HolidayListRead.model_validate(hl)


@router.post("/lists", response_model=HolidayListRead, status_code=status.HTTP_201_CREATED)
async def create_holiday_list(
    data: HolidayListCreate,
    auto_generate_weekly_offs: bool = Query(True),
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> HolidayListRead:
    service = HolidayService(session)
    return await service.create_holiday_list(data, auto_generate_weekly_offs=auto_generate_weekly_offs)


@router.post("/lists/{list_id}/holidays", response_model=HolidayRead, status_code=status.HTTP_201_CREATED)
async def add_holiday_to_list(
    list_id: int,
    data: HolidayCreate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> HolidayRead:
    service = HolidayService(session)
    return await service.add_holiday_to_list(list_id, data)
