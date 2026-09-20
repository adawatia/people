import math
from datetime import date
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Employee, EmployeeWorkHistory


class EmployeeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _eager_options(self):
        return [
            selectinload(Employee.department),
            selectinload(Employee.unit),
            selectinload(Employee.designation_rel),
            selectinload(Employee.shift),
            selectinload(Employee.reporting_manager),
            selectinload(Employee.work_history),
        ]

    async def get_by_id(self, employee_id: int) -> Employee | None:
        stmt = (
            select(Employee)
            .options(*self._eager_options())
            .where(Employee.id == employee_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_code(self, employee_code: str) -> Employee | None:
        stmt = (
            select(Employee)
            .options(*self._eager_options())
            .where(Employee.employee_code == employee_code)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> Employee | None:
        stmt = (
            select(Employee)
            .options(*self._eager_options())
            .where(Employee.user_id == user_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> Employee | None:
        stmt = (
            select(Employee)
            .options(*self._eager_options())
            .where(Employee.official_email == email)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        q: str | None = None,
        unit_id: int | None = None,
        department_id: int | None = None,
        designation_id: int | None = None,
        status: str | None = None,
        reporting_manager_id: int | None = None,
    ) -> tuple[list[Employee], int]:
        base_query = select(Employee).options(*self._eager_options())

        if q:
            term = f"%{q}%"
            base_query = base_query.where(
                or_(
                    Employee.employee_code.ilike(term),
                    Employee.first_name.ilike(term),
                    Employee.last_name.ilike(term),
                    Employee.designation.ilike(term),
                    Employee.official_email.ilike(term),
                )
            )
        if unit_id is not None:
            base_query = base_query.where(Employee.unit_id == unit_id)
        if department_id is not None:
            base_query = base_query.where(Employee.department_id == department_id)
        if designation_id is not None:
            base_query = base_query.where(Employee.designation_id == designation_id)
        if status is not None:
            base_query = base_query.where(Employee.status == status.upper())
        if reporting_manager_id is not None:
            base_query = base_query.where(Employee.reporting_manager_id == reporting_manager_id)

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        offset = (page - 1) * page_size
        stmt = base_query.order_by(Employee.employee_code).offset(offset).limit(page_size)
        employees = list((await self.session.execute(stmt)).scalars().all())

        return employees, total

    async def list_employees(
        self,
        unit_id: int | None = None,
        status: str | None = None,
        page_size: int = 1000,
    ) -> list[Employee]:
        """Flat (non-paginated) employee list used by batch processing jobs."""
        stmt = select(Employee).options(*self._eager_options())
        if unit_id is not None:
            stmt = stmt.where(Employee.unit_id == unit_id)
        if status is not None:
            stmt = stmt.where(Employee.status == status.upper())
        stmt = stmt.order_by(Employee.employee_code).limit(page_size)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, employee: Employee) -> Employee:
        self.session.add(employee)
        await self.session.flush()
        return employee

    async def delete(self, employee: Employee) -> None:
        await self.session.delete(employee)
        await self.session.flush()

    async def add_work_history(self, history: EmployeeWorkHistory) -> EmployeeWorkHistory:
        self.session.add(history)
        await self.session.flush()
        return history

    async def get_work_history(self, employee_id: int) -> list[EmployeeWorkHistory]:
        stmt = (
            select(EmployeeWorkHistory)
            .options(
                selectinload(EmployeeWorkHistory.unit),
                selectinload(EmployeeWorkHistory.department),
                selectinload(EmployeeWorkHistory.designation),
            )
            .where(EmployeeWorkHistory.employee_id == employee_id)
            .order_by(EmployeeWorkHistory.from_date.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())
