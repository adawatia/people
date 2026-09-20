from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas import UnitCreate, UnitRead, UnitUpdate
from services.org_service import OrgService

router = APIRouter(prefix="/org/units", tags=["units"])


@router.get("", response_model=list[UnitRead])
async def list_units(
    organization_id: int | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[UnitRead]:
    service = OrgService(session)
    return await service.list_units(organization_id=organization_id)


@router.get("/{unit_id}", response_model=UnitRead)
async def get_unit(
    unit_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UnitRead:
    service = OrgService(session)
    unit = await service.get_unit(unit_id)
    return UnitRead.model_validate(unit)


@router.post("", response_model=UnitRead, status_code=status.HTTP_201_CREATED)
async def create_unit(
    data: UnitCreate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> UnitRead:
    service = OrgService(session)
    return await service.create_unit(data)


@router.patch("/{unit_id}", response_model=UnitRead)
async def update_unit(
    unit_id: int,
    data: UnitUpdate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> UnitRead:
    service = OrgService(session)
    return await service.update_unit(unit_id, data)


@router.delete("/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unit(
    unit_id: int,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    service = OrgService(session)
    await service.delete_unit(unit_id)
