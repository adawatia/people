from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.pagination import ordered, paginate
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
        ]

    async def get_by_id(self, employee_id: int) -> Employee | None:
        stmt = select(Employee).options(*self._eager_options()).where(Employee.id == employee_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_erp_id(self, erp_id: str) -> Employee | None:
        stmt = select(Employee).options(*self._eager_options()).where(Employee.erp_id == erp_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_ids(self, employee_ids: list[int]) -> list[Employee]:
        if not employee_ids:
            return []
        stmt = select(Employee).options(*self._eager_options()).where(Employee.id.in_(employee_ids))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_code(self, employee_code: str) -> Employee | None:
        stmt = select(Employee).options(*self._eager_options()).where(Employee.employee_code == employee_code)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> Employee | None:
        stmt = select(Employee).options(*self._eager_options()).where(Employee.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> Employee | None:
        stmt = select(Employee).options(*self._eager_options()).where(Employee.official_email == email)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 25,
        q: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
        unit_id: int | None = None,
        department_id: int | None = None,
        designation_id: int | None = None,
        status: str | None = None,
        reporting_manager_id: int | None = None,
        allowed_employee_ids: set[int] | None = None,
        allowed_unit_ids: set[int] | None = None,
        allowed_department_ids: set[int] | None = None,
    ) -> tuple[list[Employee], int]:
        base_query = select(Employee).options(*self._eager_options())

        if q:
            term = q.strip()
            base_query = base_query.where(
                or_(
                    Employee.employee_code.icontains(term, autoescape=True),
                    Employee.first_name.icontains(term, autoescape=True),
                    Employee.last_name.icontains(term, autoescape=True),
                    Employee.designation.icontains(term, autoescape=True),
                    Employee.official_email.icontains(term, autoescape=True),
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
        if allowed_employee_ids is not None:
            base_query = base_query.where(Employee.id.in_(allowed_employee_ids))
        elif allowed_unit_ids or allowed_department_ids:
            scope_filters = []
            if allowed_unit_ids:
                scope_filters.append(Employee.unit_id.in_(allowed_unit_ids))
            if allowed_department_ids:
                scope_filters.append(Employee.department_id.in_(allowed_department_ids))
            base_query = base_query.where(or_(*scope_filters))

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            ordered(
                base_query,
                {
                    "employee_code": Employee.employee_code,
                    "name": Employee.first_name,
                    "created_at": Employee.created_at,
                    "status": Employee.status,
                },
                sort_by,
                sort_order,
                "employee_code",
                Employee.id,
            )
            .offset(offset)
            .limit(page_size)
        )
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
        stmt = stmt.order_by(Employee.employee_code, Employee.id).limit(page_size)
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

    async def work_history_page(
        self,
        employee_id,
        page=1,
        page_size=25,
        search=None,
        sort_by=None,
        sort_order="desc",
    ):
        query = (
            select(EmployeeWorkHistory)
            .options(
                selectinload(EmployeeWorkHistory.unit),
                selectinload(EmployeeWorkHistory.department),
                selectinload(EmployeeWorkHistory.designation),
            )
            .where(EmployeeWorkHistory.employee_id == employee_id)
        )
        if search:
            query = query.where(EmployeeWorkHistory.remarks.icontains(search.strip(), autoescape=True))
        query = ordered(
            query,
            {
                "from_date": EmployeeWorkHistory.from_date,
                "to_date": EmployeeWorkHistory.to_date,
                "created_at": EmployeeWorkHistory.created_at,
                "id": EmployeeWorkHistory.id,
            },
            sort_by,
            sort_order,
            "from_date",
            EmployeeWorkHistory.id,
        )
        return await paginate(self.session, query, page, page_size)
