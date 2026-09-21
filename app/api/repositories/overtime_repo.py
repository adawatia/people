from datetime import date
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AttendanceRecord, Employee, OvertimeApproval, OvertimeRecord


class OvertimeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_records(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[OvertimeRecord]:
        stmt = select(OvertimeRecord)
        if employee_id is not None:
            stmt = stmt.where(OvertimeRecord.employee_id == employee_id)
        if status is not None:
            stmt = stmt.where(OvertimeRecord.status == status.upper())
        if unit_ids or department_ids:
            stmt = stmt.join(Employee, OvertimeRecord.employee_id == Employee.id)
            filters = []
            if unit_ids:
                filters.append(Employee.unit_id.in_(unit_ids))
            if department_ids:
                filters.append(Employee.department_id.in_(department_ids))
            stmt = stmt.where(or_(*filters))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_id(self, ot_id: int) -> OvertimeRecord | None:
        return await self.session.get(OvertimeRecord, ot_id)

    async def create_approval(self, approval: OvertimeApproval) -> OvertimeApproval:
        self.session.add(approval)
        await self.session.flush()
        return approval

    async def get_records_for_period(
        self,
        employee_id: int,
        from_date: date,
        to_date: date,
    ) -> list[OvertimeRecord]:
        stmt = (
            select(OvertimeRecord)
            .join(AttendanceRecord, OvertimeRecord.attendance_record_id == AttendanceRecord.id)
            .where(
                OvertimeRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date >= from_date,
                AttendanceRecord.attendance_date <= to_date,
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())
