from db.models import now_ist

"""ERP-owned organization-wide holiday synchronization."""

from datetime import date

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_erp_api_key
from core.database import get_async_session
from db.models import Holiday, HolidayList

router = APIRouter(prefix="/integrations/erp/holidays", tags=["erp-holidays"])


class ErpHoliday(BaseModel):
    erp_holiday_id: str
    name: str
    holiday_date: date
    description: str | None = None
    is_active: bool = True


@router.post("/bulk", dependencies=[Depends(verify_erp_api_key)])
async def sync_holidays_bulk(
    holidays: list[ErpHoliday] = Body(..., min_length=1, max_length=5000),
    session: AsyncSession = Depends(get_async_session),
):
    # One organization-wide calendar is used for all employees.
    calendar = await session.scalar(select(HolidayList).where(HolidayList.is_default.is_(True)).order_by(HolidayList.id))
    if calendar is None:
        calendar = HolidayList(
            name="ERP Holiday Calendar",
            from_date=date(now_ist().date().year, 1, 1),
            to_date=date(now_ist().date().year, 12, 31),
            weekly_off_day="Sunday",
            is_default=True,
        )
        session.add(calendar)
        await session.flush()

    accepted: list[str] = []
    failed: list[dict] = []
    for item in holidays:
        try:
            holiday = await session.scalar(select(Holiday).where(Holiday.erp_holiday_id == item.erp_holiday_id))
            if holiday is None:
                holiday = Holiday(erp_holiday_id=item.erp_holiday_id, holiday_list_id=calendar.id)
                session.add(holiday)
            holiday.holiday_list_id = calendar.id
            holiday.name = item.name
            holiday.holiday_date = item.holiday_date
            holiday.description = item.description
            holiday.is_organization_wide = True
            holiday.is_weekly_off = False
            if item.is_active:
                accepted.append(item.erp_holiday_id)
            else:
                await session.delete(holiday)
        except Exception as exc:
            failed.append({"erp_holiday_id": item.erp_holiday_id, "error": str(exc)})
    await session.commit()
    return {"accepted": accepted, "failed": failed}
