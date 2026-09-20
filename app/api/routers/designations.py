from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas.designations import DesignationCreate, DesignationRead, DesignationUpdate
from services.designation_service import DesignationService

router = APIRouter(prefix="/designations", tags=["designations"])


@router.get("/", response_model=list[DesignationRead])
async def list_designations(
    is_active: bool | None = Query(None),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[DesignationRead]:
    service = DesignationService(session)
    items = await service.list_designations(is_active=is_active)
    return [DesignationRead.model_validate(d) for d in items]


@router.get("/{designation_id}", response_model=DesignationRead)
async def get_designation(
    designation_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> DesignationRead:
    service = DesignationService(session)
    designation = await service.get_designation(designation_id)
    return DesignationRead.model_validate(designation)


@router.post("/", response_model=DesignationRead, status_code=status.HTTP_201_CREATED)
async def create_designation(
    data: DesignationCreate,
    _: User = Depends(require_permission("designation.create")),
    session: AsyncSession = Depends(get_async_session),
) -> DesignationRead:
    service = DesignationService(session)
    designation = await service.create_designation(data)
    return DesignationRead.model_validate(designation)


@router.patch("/{designation_id}", response_model=DesignationRead)
async def update_designation(
    designation_id: int,
    data: DesignationUpdate,
    _: User = Depends(require_permission("designation.update")),
    session: AsyncSession = Depends(get_async_session),
) -> DesignationRead:
    service = DesignationService(session)
    designation = await service.update_designation(designation_id, data)
    return DesignationRead.model_validate(designation)


@router.delete("/{designation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_designation(
    designation_id: int,
    _: User = Depends(require_permission("designation.delete")),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    service = DesignationService(session)
    await service.delete_designation(designation_id)
