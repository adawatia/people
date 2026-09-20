from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from db.models import User
from schemas.holidays import HolidayListRead
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
