from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


from db.models import Department, Organization, Unit
from repositories.org_repo import OrgRepository
from schemas.org import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    OrganizationRead,
    UnitCreate,
    UnitRead,
    UnitUpdate,
)


class OrgService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = OrgRepository(session)

    # Organizations

    async def list_organizations(self) -> list[OrganizationRead]:
        orgs = await self.repo.list_organizations()
        return [OrganizationRead.model_validate(o) for o in orgs]


    # Units

    async def list_units(self, organization_id: int | None = None) -> list[UnitRead]:
        units = await self.repo.list_units(organization_id=organization_id)
        return [UnitRead.model_validate(u) for u in units]

    async def get_unit(self, unit_id: int) -> Unit:
        unit = await self.repo.get_unit_by_id(unit_id)
        if not unit:
            raise HTTPException(
                 status_code=status.HTTP_404_NOT_FOUND,
                 detail=f'Unit with ID {unit_id} not found',
            )
        return unit

    async def create_unit(self, data: UnitCreate) -> UnitRead:
        org = await self.repo.get_organization_by_id(data.organization_id)
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Organization with ID {data.organization_id} not found',
            )
        unit = Unit(**data.model_dump())
        created = await self.repo.create_unit(unit)
        await self.session.commit()
        return UnitRead.model_validate(created)

    async def update_unit(self, unit_id: int, data: UnitUpdate) -> UnitRead:
        unit = await self.get_unit(unit_id)
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(unit, key, value)
        await self.session.commit()
        refreshed = await self.repo.get_unit_by_id(unit_id)
        return UnitRead.model_validate(refreshed)

    # Departments

    async def list_departments(self, unit_id: int | None = None) -> list[DepartmentRead]:
        depts = await self.repo.list_departments(unit_id=unit_id)
        return [DepartmentRead.model_validate(d) for d in depts]

    async def get_department(self, dept_id: int) -> Department:
        dept = await self.repo.get_department_by_id(dept_id)
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Department with ID {dept_id} not found',
            )
        return dept

    async def create_department(self, data: DepartmentCreate) -> DepartmentRead:
        await self.get_unit(data.unit_id)
        dept = Department(**data.model_dump())
        created = await self.repo.create_department(dept)
        await self.session.commit()
        return DepartmentRead.model_validate(created)

    async def update_department(self, dept_id: int, data: DepartmentUpdate) -> DepartmentRead:
        dept = await self.get_department(dept_id)
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(dept, key, value)
        await self.session.commit()
        return DepartmentRead.model_validate(dept)
