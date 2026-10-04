from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Department, Employee, Holiday, Organization, Unit


class OrgRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Organizations ──────────────────────────────────────────────────────────

    async def get_organization(self) -> Organization | None:
        stmt = select(Organization).order_by(Organization.id).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_organization_by_erp_id(self, erp_id: str) -> Organization | None:
        return await self.session.scalar(select(Organization).where(Organization.erp_id == erp_id))

    async def create_organization(self, organization: Organization) -> Organization:
        self.session.add(organization)
        await self.session.flush()
        return organization

    # ── Units ──────────────────────────────────────────────────────────────────

    async def list_units(self, organization_id: int | None = None) -> list[Unit]:
        stmt = select(Unit).options(selectinload(Unit.departments)).order_by(Unit.name)
        if organization_id is not None:
            stmt = stmt.where(Unit.organization_id == organization_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_unit_by_id(self, unit_id: int) -> Unit | None:
        stmt = select(Unit).options(selectinload(Unit.departments)).where(Unit.id == unit_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_unit_by_erp_id(self, erp_id: str) -> Unit | None:
        stmt = select(Unit).options(selectinload(Unit.departments)).where(Unit.erp_id == erp_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_unit(self, unit: Unit) -> Unit:
        self.session.add(unit)
        await self.session.flush()
        return await self.get_unit_by_id(unit.id)  # type: ignore[return-value]

    async def count_unit_blocking_dependencies(self, unit_id: int) -> int:
        dept_ids = select(Department.id).where(Department.unit_id == unit_id)
        employee_stmt = select(func.count(Employee.id)).where(
            (Employee.unit_id == unit_id) | (Employee.department_id.in_(dept_ids))
        )
        holiday_stmt = select(func.count(Holiday.id)).where(Holiday.unit_id == unit_id)
        employee_count = await self.session.scalar(employee_stmt)
        holiday_count = await self.session.scalar(holiday_stmt)
        return int(employee_count or 0) + int(holiday_count or 0)

    async def delete_unit(self, unit: Unit) -> None:
        await self.session.delete(unit)
        await self.session.flush()

    # ── Departments ────────────────────────────────────────────────────────────

    async def list_departments(self, unit_id: int | None = None) -> list[Department]:
        stmt = select(Department).options(selectinload(Department.unit)).order_by(Department.name)
        if unit_id is not None:
            stmt = stmt.where(Department.unit_id == unit_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_department_by_id(self, dept_id: int) -> Department | None:
        return await self.session.get(Department, dept_id)

    async def get_department_by_erp_id(self, erp_id: str) -> Department | None:
        return await self.session.scalar(select(Department).where(Department.erp_id == erp_id))

    async def create_department(self, department: Department) -> Department:
        self.session.add(department)
        await self.session.flush()
        return department

    async def count_department_blocking_dependencies(self, dept_id: int) -> int:
        employee_stmt = select(func.count(Employee.id)).where(Employee.department_id == dept_id)
        employee_count = await self.session.scalar(employee_stmt)
        return int(employee_count or 0)

    async def delete_department(self, department: Department) -> None:
        await self.session.delete(department)
        await self.session.flush()
