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
    DepartmentUpsert,
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

    async def upsert_organization(self, erp_id: str, data: OrganizationUpdate | OrganizationCreate) -> OrganizationRead:
        # The organization is a singleton: lock that row's identity, even when
        # requests use different ERP IDs.
        await acquire_erp_upsert_lock(self.session, "organization", "singleton")
        fields = data.model_dump(exclude_unset=True)
        if "name" in fields and not fields["name"]:
            raise HTTPException(status_code=422, detail="name cannot be empty")
        try:
            org = await self.repo.get_organization()
            if org is None:
                if not fields.get("name"):
                    raise HTTPException(status_code=422, detail="name is required when creating the organization")
                org = await self.repo.create_organization(Organization(**fields, erp_id=erp_id))
            else:
                for key, value in fields.items():
                    setattr(org, key, value)
                org.erp_id = erp_id
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(status_code=409, detail="Organization conflicts with existing master data") from exc
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

    async def upsert_unit(self, erp_id: str, data: UnitUpdate) -> UnitRead:
        await acquire_erp_upsert_lock(self.session, "unit", erp_id)
        if "name" in data.model_fields_set and not data.name:
            raise HTTPException(status_code=422, detail="name cannot be empty")
        if "is_active" in data.model_fields_set and data.is_active is None:
            raise HTTPException(status_code=422, detail="is_active cannot be null")
        unit = await self.repo.get_unit_by_erp_id(erp_id)
        try:
            if unit is None:
                if not data.name:
                    raise HTTPException(status_code=422, detail="name is required when creating a unit")
                org = await self.repo.get_organization()
                if org is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, detail="Organization must be synced first"
                    )
                unit = await self.repo.create_unit(
                    Unit(
                        **UnitCreate.model_validate(data.model_dump(exclude_unset=True)).model_dump(),
                        organization_id=org.id,
                        erp_id=erp_id,
                    )
                )
            else:
                for key, value in data.model_dump(exclude_unset=True).items():
                    setattr(unit, key, value)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(status_code=409, detail="Unit conflicts with existing master data") from exc
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
        return [
            DepartmentRead.model_validate(dept).model_copy(
                update={"unit_is_active": dept.unit.is_active if dept.unit else False}
            )
            for dept in depts
        ]

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

    async def upsert_department(self, erp_id: str, data: DepartmentUpsert) -> DepartmentRead:
        await acquire_erp_upsert_lock(self.session, "department", erp_id)
        if "name" in data.model_fields_set and not data.name:
            raise HTTPException(status_code=422, detail="name cannot be empty")
        if "unit_id" in data.model_fields_set and data.unit_id is None:
            raise HTTPException(status_code=422, detail="unit_id cannot be null")
        if "is_active" in data.model_fields_set and data.is_active is None:
            raise HTTPException(status_code=422, detail="is_active cannot be null")
        department = await self.repo.get_department_by_erp_id(erp_id)
        try:
            if department is None:
                if not data.name or data.unit_id is None:
                    raise HTTPException(
                        status_code=422, detail="name and unit_id are required when creating a department"
                    )
                unit = await self.get_unit(data.unit_id)
                if unit.is_active is False and data.is_active is not False:
                    raise HTTPException(
                        status_code=409,
                        detail="An active department cannot be created under an inactive unit",
                    )
                department = await self.repo.create_department(
                    Department(
                        **DepartmentCreate.model_validate(data.model_dump(exclude_unset=True)).model_dump(),
                        erp_id=erp_id,
                    )
                )
            else:
                if data.unit_id is not None:
                    unit = await self.get_unit(data.unit_id)
                    will_be_active = data.is_active if data.is_active is not None else department.is_active
                    if (
                        unit.is_active is False
                        and will_be_active
                        and (data.unit_id != department.unit_id or data.is_active is True)
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail="An active department cannot be assigned to an inactive unit",
                        )
                elif data.is_active is True:
                    unit = await self.get_unit(department.unit_id)
                    if unit.is_active is False:
                        raise HTTPException(
                            status_code=409,
                            detail="A department cannot be activated while its unit is inactive",
                        )
                for key, value in data.model_dump(exclude_unset=True).items():
                    setattr(department, key, value)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(status_code=409, detail="Department conflicts with existing master data") from exc
        await self.session.refresh(department)
        unit = await self.get_unit(department.unit_id)
        return DepartmentRead.model_validate(department).model_copy(update={"unit_is_active": unit.is_active})

    async def delete_department(self, dept_id: int) -> None:
        dept = await self.get_department(dept_id)
        dept.is_active = False
        await self.session.commit()
