from datetime import date
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Employee, WorkArrangementRequest


class WorkArrangementRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, request_id: int) -> WorkArrangementRequest | None:
        stmt = (
            select(WorkArrangementRequest)
            .options(selectinload(WorkArrangementRequest.employee))
            .where(WorkArrangementRequest.id == request_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, req: WorkArrangementRequest) -> WorkArrangementRequest:
        self.session.add(req)
        await self.session.flush()
        return req

    async def find_overlapping(
        self,
        employee_id: int,
        from_date: date,
        to_date: date,
        exclude_id: int | None = None,
    ) -> WorkArrangementRequest | None:
        stmt = select(WorkArrangementRequest).where(
            WorkArrangementRequest.employee_id == employee_id,
            WorkArrangementRequest.status.in_(["PENDING", "APPROVED"]),
            WorkArrangementRequest.from_date <= to_date,
            WorkArrangementRequest.to_date >= from_date,
        )
        if exclude_id is not None:
            stmt = stmt.where(WorkArrangementRequest.id != exclude_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_requests(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        arrangement_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[WorkArrangementRequest]:
        stmt = (
            select(WorkArrangementRequest)
            .options(selectinload(WorkArrangementRequest.employee))
            .order_by(WorkArrangementRequest.created_at.desc())
        )
        if employee_id is not None:
            stmt = stmt.where(WorkArrangementRequest.employee_id == employee_id)
        elif unit_ids or department_ids:
            stmt = stmt.join(Employee, WorkArrangementRequest.employee_id == Employee.id)
            filters = []
            if unit_ids:
                filters.append(Employee.unit_id.in_(unit_ids))
            if department_ids:
                filters.append(Employee.department_id.in_(department_ids))
            stmt = stmt.where(or_(*filters))
        if status is not None:
            stmt = stmt.where(WorkArrangementRequest.status == status.upper())
        if arrangement_type is not None:
            stmt = stmt.where(WorkArrangementRequest.arrangement_type == arrangement_type.upper())
        if from_date is not None:
            stmt = stmt.where(WorkArrangementRequest.to_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(WorkArrangementRequest.from_date <= to_date)
        return list((await self.session.execute(stmt)).scalars().all())
