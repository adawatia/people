from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from core.pagination import PaginatedResponse
from db.models import Department, User
from schemas import DepartmentRead
from services.lookup_service import LookupService
from services.org_service import OrgService

router = APIRouter(prefix="/org/departments", tags=["departments"])


@router.get("", response_model=PaginatedResponse[DepartmentRead])
async def list_departments(
    unit_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[DepartmentRead]:
    return await LookupService(session).list_page(Department, page=page, page_size=page_size,
        search=search, sort_by=sort_by, sort_order=sort_order, filters={"unit_id": unit_id})


@router.get("/{dept_id}", response_model=DepartmentRead)
async def get_department(
    dept_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> DepartmentRead:
    service = OrgService(session)
    dept = await service.get_department(dept_id)
    return DepartmentRead.model_validate(dept)
