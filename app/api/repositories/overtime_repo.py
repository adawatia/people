from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from core.pagination import ordered, paginate
from db.models import AttendanceRecord, Employee, OvertimeApproval, OvertimeRecord


class OvertimeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def records_query(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        q: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ):
        stmt = (
            select(OvertimeRecord)
            .join(OvertimeRecord.employee)
            .join(OvertimeRecord.attendance_record)
            .options(contains_eager(OvertimeRecord.employee), contains_eager(OvertimeRecord.attendance_record))
        )
        if employee_id is not None:
            stmt = stmt.where(OvertimeRecord.employee_id == employee_id)
        if status is not None:
            stmt = stmt.where(OvertimeRecord.status == status.upper())
        if unit_ids or department_ids:
            filters = []
            if unit_ids:
                filters.append(Employee.unit_id.in_(unit_ids))
            if department_ids:
                filters.append(Employee.department_id.in_(department_ids))
            stmt = stmt.where(or_(*filters))
        if from_date is not None:
            stmt = stmt.where(AttendanceRecord.attendance_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(AttendanceRecord.attendance_date <= to_date)
        if q and q.strip():
            name = Employee.first_name + " " + func.coalesce(Employee.last_name, "")
            stmt = stmt.where(or_(
                name.icontains(q.strip(), autoescape=True),
                Employee.employee_code.icontains(q.strip(), autoescape=True),
            ))
        return ordered(stmt, {"attendance_date": AttendanceRecord.attendance_date, "status": OvertimeRecord.status,
                              "id": OvertimeRecord.id}, sort_by, sort_order, "attendance_date", OvertimeRecord.id)

    async def list_records(self, **filters) -> list[OvertimeRecord]:
        stmt = self.records_query(**filters)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_page(self, *, page: int, page_size: int, **filters) -> dict:
        return await paginate(self.session, self.records_query(**filters), page=page, page_size=page_size)

    async def get_by_id(self, ot_id: int) -> OvertimeRecord | None:
        return await self.session.get(OvertimeRecord, ot_id)

    async def get_by_id_for_update(self, ot_id: int) -> OvertimeRecord | None:
        stmt = (
            select(OvertimeRecord)
            .where(OvertimeRecord.id == ot_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(stmt)

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
