from datetime import date
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Holiday, HolidayList


class HolidayRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_list_by_id(self, list_id: int) -> HolidayList | None:
        stmt = (
            select(HolidayList)
            .options(selectinload(HolidayList.holidays))
            .where(HolidayList.id == list_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_default_list(self, unit_id: int | None = None) -> HolidayList | None:
        """Finds default holiday list for a unit or org-wide."""
        stmt = (
            select(HolidayList)
            .options(selectinload(HolidayList.holidays))
            .where(HolidayList.is_default == True)
        )
        if unit_id is not None:
            # Prefer unit-specific default, fallback to org-wide
            unit_stmt = stmt.where(HolidayList.unit_id == unit_id)
            res = (await self.session.execute(unit_stmt)).scalar_one_or_none()
            if res:
                return res
        org_stmt = stmt.where(HolidayList.unit_id.is_(None))
        return (await self.session.execute(org_stmt)).scalar_one_or_none()

    async def list_holiday_lists(self, unit_id: int | None = None) -> list[HolidayList]:
        stmt = select(HolidayList).options(selectinload(HolidayList.holidays))
        if unit_id is not None:
            stmt = stmt.where(or_(HolidayList.unit_id == unit_id, HolidayList.unit_id.is_(None)))
        stmt = stmt.order_by(HolidayList.from_date.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_holiday_list(self, holiday_list: HolidayList) -> HolidayList:
        self.session.add(holiday_list)
        await self.session.flush()
        return holiday_list

    async def add_holiday(self, holiday: Holiday) -> Holiday:
        self.session.add(holiday)
        await self.session.flush()
        return holiday

    async def get_holidays_between(
        self,
        holiday_list_id: int,
        from_date: date,
        to_date: date,
        include_weekly_offs: bool = True,
    ) -> list[Holiday]:
        stmt = select(Holiday).where(
            Holiday.holiday_list_id == holiday_list_id,
            Holiday.holiday_date >= from_date,
            Holiday.holiday_date <= to_date,
        )
        if not include_weekly_offs:
            stmt = stmt.where(Holiday.is_weekly_off == False)
        stmt = stmt.order_by(Holiday.holiday_date)
        return list((await self.session.execute(stmt)).scalars().all())
