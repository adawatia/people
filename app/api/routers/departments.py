from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import current_active_user
from core.database import get_async_session
from core.pagination import PaginatedResponse
from core.sorting import LookupSort
from db.models import Department, Unit, User
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
    sort_by: LookupSort | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    _: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[DepartmentRead]:
    result = await LookupService(session).list_page(
        Department,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters={"unit_id": unit_id},
    )
    unit_ids = {item.unit_id for item in result["items"]}
    units = await session.scalars(select(Unit).where(Unit.id.in_(unit_ids))) if unit_ids else []
    unit_active_by_id = {unit.id: unit.is_active for unit in units}
    result["items"] = [
        DepartmentRead.model_validate(item).model_copy(update={"unit_is_active": unit_active_by_id.get(item.unit_id)})
        for item in result["items"]
    ]
    return result


@router.get("/{dept_id}", response_model=DepartmentRead)
async def get_department(
    dept_id: int,
    _: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> DepartmentRead:
    service = OrgService(session)
    dept = await service.get_department(dept_id)
    unit = await session.get(Unit, dept.unit_id)
    return DepartmentRead.model_validate(dept).model_copy(update={"unit_is_active": unit.is_active if unit else False})
