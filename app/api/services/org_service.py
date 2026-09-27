from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.erp_sync import acquire_erp_upsert_lock
from db.models import Department, Organization, Unit
from repositories.org_repo import OrgRepository
from schemas.org import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    UnitCreate,
    UnitRead,
    UnitUpdate,
)


class OrgService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = OrgRepository(session)

    # Organizations

    async def get_organization(self) -> OrganizationRead:
        org = await self.repo.get_organization()
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        return OrganizationRead.model_validate(org)

    async def create_organization(self, data: OrganizationCreate) -> OrganizationRead:
        existing = await self.repo.get_organization()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization already exists",
            )
        org = Organization(**data.model_dump())
        created = await self.repo.create_organization(org)
        await self.session.commit()
        return OrganizationRead.model_validate(created)

    async def update_organization(self, data: OrganizationUpdate) -> OrganizationRead:
        org = await self.repo.get_organization()
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(org, key, value)
        await self.session.commit()
        return OrganizationRead.model_validate(org)

    async def upsert_organization(self, erp_id: str, data: OrganizationCreate) -> OrganizationRead:
        await acquire_erp_upsert_lock(self.session, "organization", erp_id)
        org = await self.repo.get_organization_by_erp_id(erp_id)
        if org is None:
            org = await self.repo.get_organization()
        if org is None:
            org = await self.repo.create_organization(Organization(**data.model_dump(), erp_id=erp_id))
        else:
            for key, value in data.model_dump().items():
                setattr(org, key, value)
            org.erp_id = erp_id
        await self.session.commit()
        await self.session.refresh(org)
        return OrganizationRead.model_validate(org)

    # Units

    async def list_units(self, organization_id: int | None = None) -> list[UnitRead]:
        units = await self.repo.list_units(organization_id=organization_id)
        return [UnitRead.model_validate(u) for u in units]

    async def get_unit(self, unit_id: int) -> Unit:
        unit = await self.repo.get_unit_by_id(unit_id)
        if not unit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unit with ID {unit_id} not found",
            )
        return unit

    async def create_unit(self, data: UnitCreate) -> UnitRead:
        org = await self.repo.get_organization()
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        unit = Unit(**data.model_dump(), organization_id=org.id)
        try:
            created = await self.repo.create_unit(unit)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A unit with code '{data.code}' already exists",
            ) from exc
        return UnitRead.model_validate(created)

    async def update_unit(self, unit_id: int, data: UnitUpdate) -> UnitRead:
        unit = await self.get_unit(unit_id)
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(unit, key, value)
        await self.session.commit()
        refreshed = await self.repo.get_unit_by_id(unit_id)
        return UnitRead.model_validate(refreshed)

    async def upsert_unit(self, erp_id: str, data: UnitCreate) -> UnitRead:
        await acquire_erp_upsert_lock(self.session, "unit", erp_id)
        unit = await self.repo.get_unit_by_erp_id(erp_id)
        if unit is None:
            org = await self.repo.get_organization()
            if org is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization must be synced first")
            unit = await self.repo.create_unit(Unit(**data.model_dump(), organization_id=org.id, erp_id=erp_id))
        else:
            for key, value in data.model_dump().items():
                setattr(unit, key, value)
        await self.session.commit()
        refreshed = await self.repo.get_unit_by_erp_id(erp_id)
        return UnitRead.model_validate(refreshed)

    async def delete_unit(self, unit_id: int) -> None:
        unit = await self.get_unit(unit_id)
        # ERP master-data history is referenced by employee and attendance
        # records. A DELETE therefore means tombstone, never physical removal.
        unit.is_active = False
        await self.session.commit()

    # Departments

    async def list_departments(self, unit_id: int | None = None) -> list[DepartmentRead]:
        depts = await self.repo.list_departments(unit_id=unit_id)
        return [DepartmentRead.model_validate(d) for d in depts]

    async def get_department(self, dept_id: int) -> Department:
        dept = await self.repo.get_department_by_id(dept_id)
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department with ID {dept_id} not found",
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

    async def upsert_department(self, erp_id: str, data: DepartmentCreate) -> DepartmentRead:
        await acquire_erp_upsert_lock(self.session, "department", erp_id)
        await self.get_unit(data.unit_id)
        department = await self.repo.get_department_by_erp_id(erp_id)
        if department is None:
            department = await self.repo.create_department(Department(**data.model_dump(), erp_id=erp_id))
        else:
            for key, value in data.model_dump().items():
                setattr(department, key, value)
        await self.session.commit()
        await self.session.refresh(department)
        return DepartmentRead.model_validate(department)

    async def delete_department(self, dept_id: int) -> None:
        dept = await self.get_department(dept_id)
        dept.is_active = False
        await self.session.commit()
