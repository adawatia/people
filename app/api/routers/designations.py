from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import current_business_user
from core.database import get_async_session
from core.pagination import PaginatedResponse
from core.sorting import LookupSort
from db.models import Designation, User
from schemas.designations import DesignationRead
from services.designation_service import DesignationService
from services.lookup_service import LookupService

router = APIRouter(prefix="/designations", tags=["designations"])


@router.get("/", response_model=PaginatedResponse[DesignationRead])
async def list_designations(
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: LookupSort | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    _: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[DesignationRead]:
    return await LookupService(session).list_page(
        Designation,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters={"is_active": is_active},
    )


@router.get("/{designation_id}", response_model=DesignationRead)
async def get_designation(
    designation_id: int,
    _: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> DesignationRead:
    service = DesignationService(session)
    designation = await service.get_designation(designation_id)
    return DesignationRead.model_validate(designation)
