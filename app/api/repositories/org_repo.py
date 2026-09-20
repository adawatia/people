from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Department, Organization, Unit


class OrgRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Organizations ──────────────────────────────────────────────────────────

    async def list_organizations(self) -> list[Organization]:
        stmt = select(Organization).order_by(Organization.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_organization_by_id(self, org_id: int) -> Organization | None:
        return await self.session.get(Organization, org_id)

    # ── Units ──────────────────────────────────────────────────────────────────

    async def list_units(self, organization_id: int | None = None) -> list[Unit]:
        stmt = select(Unit).options(selectinload(Unit.departments)).order_by(Unit.name)
        if organization_id is not None:
            stmt = stmt.where(Unit.organization_id == organization_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_unit_by_id(self, unit_id: int) -> Unit | None:
        stmt = select(Unit).options(selectinload(Unit.departments)).where(Unit.id == unit_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_unit(self, unit: Unit) -> Unit:
        self.session.add(unit)
        await self.session.flush()
        return await self.get_unit_by_id(unit.id)  # type: ignore[return-value]

    # ── Departments ────────────────────────────────────────────────────────────

    async def list_departments(self, unit_id: int | None = None) -> list[Department]:
        stmt = select(Department).order_by(Department.name)
        if unit_id is not None:
            stmt = stmt.where(Department.unit_id == unit_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_department_by_id(self, dept_id: int) -> Department | None:
        return await self.session.get(Department, dept_id)

    async def create_department(self, department: Department) -> Department:
        self.session.add(department)
        await self.session.flush()
        return department
