from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import AttendanceCorrectionRequest, AttendanceRecord, Employee


class AttendanceRecordRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, record_id: int) -> AttendanceRecord | None:
        stmt = (
            select(AttendanceRecord)
            .options(
                selectinload(AttendanceRecord.employee),
                selectinload(AttendanceRecord.shift),
            )
            .where(AttendanceRecord.id == record_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_employee_and_date(self, employee_id: int, target_date: date) -> AttendanceRecord | None:
        stmt = (
            select(AttendanceRecord)
            .options(
                selectinload(AttendanceRecord.employee),
                selectinload(AttendanceRecord.shift),
            )
            .where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date == target_date,
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, record: AttendanceRecord) -> AttendanceRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_records(
        self,
        employee_id: int | None = None,
        unit_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[AttendanceRecord]:
        stmt = (
            select(AttendanceRecord)
            .options(
                selectinload(AttendanceRecord.employee),
                selectinload(AttendanceRecord.shift),
            )
            .order_by(AttendanceRecord.attendance_date.desc(), AttendanceRecord.employee_id)
        )
        if employee_id is not None:
            stmt = stmt.where(AttendanceRecord.employee_id == employee_id)
        if from_date is not None:
            stmt = stmt.where(AttendanceRecord.attendance_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(AttendanceRecord.attendance_date <= to_date)
        if status is not None:
            stmt = stmt.where(AttendanceRecord.status == status.upper())
        if unit_id is not None:
            stmt = stmt.join(Employee, AttendanceRecord.employee_id == Employee.id).where(
                Employee.unit_id == unit_id
            )

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_month_records(
        self,
        employee_id: int,
        from_date: date,
        to_date: date,
    ) -> list[AttendanceRecord]:
        stmt = (
            select(AttendanceRecord)
            .where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date >= from_date,
                AttendanceRecord.attendance_date <= to_date,
            )
            .order_by(AttendanceRecord.attendance_date.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_correction_by_id(self, correction_id: int) -> AttendanceCorrectionRequest | None:
        stmt = (
            select(AttendanceCorrectionRequest)
            .where(AttendanceCorrectionRequest.id == correction_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_correction(self, correction: AttendanceCorrectionRequest) -> AttendanceCorrectionRequest:
        self.session.add(correction)
        await self.session.flush()
        return correction

    async def list_corrections(self, status: str | None = None) -> list[AttendanceCorrectionRequest]:
        stmt = select(AttendanceCorrectionRequest).order_by(AttendanceCorrectionRequest.requested_at.desc())
        if status is not None:
            stmt = stmt.where(AttendanceCorrectionRequest.status == status.upper())
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, record: AttendanceRecord) -> None:
        await self.session.delete(record)
        await self.session.flush()

