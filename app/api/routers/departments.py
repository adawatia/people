from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from db.models import User
from schemas import DepartmentRead
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
