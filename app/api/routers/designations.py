from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from db.models import User
from schemas.designations import DesignationRead
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
