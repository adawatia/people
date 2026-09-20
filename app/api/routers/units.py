from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from db.models import User
from schemas import UnitRead
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
