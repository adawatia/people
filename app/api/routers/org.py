from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    OrganizationRead,
    UnitCreate,
    UnitRead,
    UnitUpdate,
)
from services.org_service import OrgService

router = APIRouter(prefix="/org", tags=["organization"])


# -----------------------------------------------------------------------------
# Organizations
# -----------------------------------------------------------------------------

@router.get("/organizations", response_model=list[OrganizationRead])
async def list_organizations(
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[OrganizationRead]:
    service = OrgService(session)
    return await service.list_organizations()


# -----------------------------------------------------------------------------
# Units
# -----------------------------------------------------------------------------

@router.get("/units", response_model=list[UnitRead])
async def list_units(
    organization_id: int | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[UnitRead]:
    service = OrgService(session)
    return await service.list_units(organization_id=organization_id)


@router.get("/units/{unit_id}", response_model=UnitRead)
async def get_unit(
    unit_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UnitRead:
    service = OrgService(session)
    unit = await service.get_unit(unit_id)
    return UnitRead.model_validate(unit)


@router.post("/units", response_model=UnitRead, status_code=status.HTTP_201_CREATED)
async def create_unit(
    data: UnitCreate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> UnitRead:
    service = OrgService(session)
    return await service.create_unit(data)


@router.patch("/units/{unit_id}", response_model=UnitRead)
async def update_unit(
    unit_id: int,
    data: UnitUpdate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> UnitRead:
    service = OrgService(session)
    return await service.update_unit(unit_id, data)


# -----------------------------------------------------------------------------
# Departments
# -----------------------------------------------------------------------------

@router.get("/departments", response_model=list[DepartmentRead])
async def list_departments(
    unit_id: int | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[DepartmentRead]:
    service = OrgService(session)
    return await service.list_departments(unit_id=unit_id)


@router.get("/departments/{dept_id}", response_model=DepartmentRead)
async def get_department(
    dept_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> DepartmentRead:
    service = OrgService(session)
    dept = await service.get_department(dept_id)
    return DepartmentRead.model_validate(dept)


@router.post("/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
async def create_department(
    data: DepartmentCreate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> DepartmentRead:
    service = OrgService(session)
    return await service.create_department(data)


@router.patch("/departments/{dept_id}", response_model=DepartmentRead)
async def update_department(
    dept_id: int,
    data: DepartmentUpdate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> DepartmentRead:
    service = OrgService(session)
    return await service.update_department(dept_id, data)

