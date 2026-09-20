from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas import DepartmentCreate, DepartmentRead, DepartmentUpdate
from services.org_service import OrgService

router = APIRouter(prefix="/org/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentRead])
async def list_departments(
    unit_id: int | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[DepartmentRead]:
    service = OrgService(session)
    return await service.list_departments(unit_id=unit_id)


@router.get("/{dept_id}", response_model=DepartmentRead)
async def get_department(
    dept_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> DepartmentRead:
    service = OrgService(session)
    dept = await service.get_department(dept_id)
    return DepartmentRead.model_validate(dept)


@router.post("", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
async def create_department(
    data: DepartmentCreate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> DepartmentRead:
    service = OrgService(session)
    return await service.create_department(data)


@router.patch("/{dept_id}", response_model=DepartmentRead)
async def update_department(
    dept_id: int,
    data: DepartmentUpdate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> DepartmentRead:
    service = OrgService(session)
    return await service.update_department(dept_id, data)


@router.delete("/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    dept_id: int,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    service = OrgService(session)
    await service.delete_department(dept_id)
