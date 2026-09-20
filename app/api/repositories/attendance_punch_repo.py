from datetime import datetime
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import AttendancePunch, Employee


class AttendancePunchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, punch_id: int) -> AttendancePunch | None:
        stmt = (
            select(AttendancePunch)
            .options(selectinload(AttendancePunch.shift), selectinload(AttendancePunch.employee))
            .where(AttendancePunch.id == punch_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_duplicate(
        self,
        employee_id: int,
        punch_time: datetime,
        punch_type: str,
    ) -> AttendancePunch | None:
        # Microsecond precision stripped for duplicate check
        clean_time = punch_time.replace(microsecond=0)
        stmt = select(AttendancePunch).where(
            AttendancePunch.employee_id == employee_id,
            AttendancePunch.punch_time == clean_time,
            AttendancePunch.punch_type == punch_type,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def create(self, punch: AttendancePunch) -> AttendancePunch:
        self.session.add(punch)
        await self.session.flush()
        return punch

    async def list_punches(
        self,
        employee_id: int | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        is_processed: bool | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[AttendancePunch]:
        stmt = (
            select(AttendancePunch)
            .options(selectinload(AttendancePunch.shift), selectinload(AttendancePunch.employee))
            .order_by(AttendancePunch.punch_time.asc())
        )
        if employee_id is not None:
            stmt = stmt.where(AttendancePunch.employee_id == employee_id)
        elif unit_ids or department_ids:
            stmt = stmt.join(Employee, AttendancePunch.employee_id == Employee.id)
            filters = []
            if unit_ids:
                filters.append(Employee.unit_id.in_(unit_ids))
            if department_ids:
                filters.append(Employee.department_id.in_(department_ids))
            stmt = stmt.where(or_(*filters))
        if from_time is not None:
            stmt = stmt.where(AttendancePunch.punch_time >= from_time)
        if to_time is not None:
            stmt = stmt.where(AttendancePunch.punch_time <= to_time)
        if is_processed is not None:
            stmt = stmt.where(AttendancePunch.is_processed == is_processed)

        return list((await self.session.execute(stmt)).scalars().all())
