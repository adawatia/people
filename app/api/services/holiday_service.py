from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Holiday, HolidayList
from repositories.employee_repo import EmployeeRepository
from repositories.holiday_repo import HolidayRepository
from schemas.holidays import (
    HolidayCreate,
    HolidayListCreate,
    HolidayListRead,
    HolidayRead,
)


class HolidayService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = HolidayRepository(session)
        self.employee_repo = EmployeeRepository(session)

    WEEKDAYS = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }

    async def list_holiday_lists(self, unit_id: int | None = None) -> list[HolidayListRead]:
        lists = await self.repo.list_holiday_lists(unit_id=unit_id)
        return [HolidayListRead.model_validate(hl) for hl in lists]

    async def get_holiday_list(self, list_id: int) -> HolidayList:
        hl = await self.repo.get_list_by_id(list_id)
        if not hl:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Holiday list with ID {list_id} not found",
            )
        return hl

    async def create_holiday_list(self, data: HolidayListCreate, auto_generate_weekly_offs: bool = True) -> HolidayListRead:
        if data.to_date < data.from_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="to_date must be greater than or equal to from_date",
            )

        hl = HolidayList(
            unit_id=data.unit_id,
            name=data.name,
            from_date=data.from_date,
            to_date=data.to_date,
            weekly_off_day=data.weekly_off_day,
            is_default=data.is_default,
        )
        created = await self.repo.create_holiday_list(hl)

        # Explicit holidays provided in payload
        existing_dates = set()
        for h in data.holidays:
            holiday_item = Holiday(
                holiday_list_id=created.id,
                unit_id=data.unit_id,
                name=h.name,
                description=h.description,
                holiday_date=h.holiday_date,
                is_weekly_off=h.is_weekly_off,
                is_organization_wide=h.is_organization_wide,
            )
            await self.repo.add_holiday(holiday_item)
            existing_dates.add(h.holiday_date)

        # Auto-generate weekly offs if requested
        if auto_generate_weekly_offs and data.weekly_off_day:
            target_weekday = self.WEEKDAYS.get(data.weekly_off_day.lower(), 6)
            curr = data.from_date
            while curr <= data.to_date:
                if curr.weekday() == target_weekday and curr not in existing_dates:
                    weekly_off = Holiday(
                        holiday_list_id=created.id,
                        unit_id=data.unit_id,
                        name=f"Weekly Off ({data.weekly_off_day})",
                        description="Scheduled weekly rest day",
                        holiday_date=curr,
                        is_weekly_off=True,
                        is_organization_wide=True,
                    )
                    await self.repo.add_holiday(weekly_off)
                    existing_dates.add(curr)
                curr += timedelta(days=1)

        await self.session.commit()
        refreshed = await self.get_holiday_list(created.id)
        return HolidayListRead.model_validate(refreshed)

    async def add_holiday_to_list(self, list_id: int, data: HolidayCreate) -> HolidayRead:
        hl = await self.get_holiday_list(list_id)
        holiday = Holiday(
            holiday_list_id=hl.id,
            unit_id=hl.unit_id,
            name=data.name,
            description=data.description,
            holiday_date=data.holiday_date,
            is_weekly_off=data.is_weekly_off,
            is_organization_wide=data.is_organization_wide,
        )
        created = await self.repo.add_holiday(holiday)
        await self.session.commit()
        return HolidayRead.model_validate(created)

    async def resolve_holiday_list_for_employee(self, employee_id: int) -> HolidayList | None:
        """Resolves active holiday list: Unit default -> Org default."""
        emp = await self.employee_repo.get_by_id(employee_id)
        unit_id = emp.unit_id if emp else None
        return await self.repo.get_default_list(unit_id=unit_id)

    async def is_holiday_or_weekly_off(
        self,
        employee_id: int,
        target_date: date,
    ) -> tuple[bool, bool, str | None]:
        """
        Returns (is_holiday_or_off, is_weekly_off, description).
        """
        hl = await self.resolve_holiday_list_for_employee(employee_id)
        if not hl:
            # Default to checking if Sunday
            if target_date.weekday() == 6:
                return True, True, "Sunday (Default Weekly Off)"
            return False, False, None

        holidays = await self.repo.get_holidays_between(hl.id, target_date, target_date, include_weekly_offs=True)
        if holidays:
            h = holidays[0]
            return True, h.is_weekly_off, h.name

        return False, False, None

    async def get_holidays_in_range(
        self,
        employee_id: int,
        from_date: date,
        to_date: date,
        skip_weekly_offs: bool = False,
    ) -> set[date]:
        """Returns the set of dates that are holidays (or weekly offs) for an employee."""
        hl = await self.resolve_holiday_list_for_employee(employee_id)
        if not hl:
            result = set()
            if not skip_weekly_offs:
                curr = from_date
                while curr <= to_date:
                    if curr.weekday() == 6:
                        result.add(curr)
                    curr += timedelta(days=1)
            return result

        holidays = await self.repo.get_holidays_between(
            hl.id, from_date, to_date, include_weekly_offs=not skip_weekly_offs
        )
        return {h.holiday_date for h in holidays}

    async def is_holiday_for_date(
        self,
        holiday_list_id: int,
        check_date: date,
        include_weekly_offs: bool = True,
    ) -> tuple[bool, str | None]:
        """Checks if a given calendar date is marked as a holiday in a holiday list."""
        holidays = await self.repo.get_holidays_between(
            holiday_list_id, check_date, check_date, include_weekly_offs=include_weekly_offs
        )
        if holidays:
            return True, holidays[0].name
        return False, None

