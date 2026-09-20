from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AttendanceRecord, OvertimeApproval, OvertimeRecord


class OvertimeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_records(
        self,
        employee_id: int | None = None,
        status: str | None = None,
    ) -> list[OvertimeRecord]:
        stmt = select(OvertimeRecord)
        if employee_id is not None:
            stmt = stmt.where(OvertimeRecord.employee_id == employee_id)
        if status is not None:
            stmt = stmt.where(OvertimeRecord.status == status.upper())
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
