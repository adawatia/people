from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas import OrganizationCreate, OrganizationRead, OrganizationUpdate
from services.org_service import OrgService

router = APIRouter(prefix="/org/organization", tags=["organization"])


@router.get("", response_model=OrganizationRead)
async def get_organization(
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    service = OrgService(session)
    return await service.get_organization()


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    service = OrgService(session)
    return await service.create_organization(data)


@router.patch("", response_model=OrganizationRead)
async def update_organization(
    data: OrganizationUpdate,
    _: User = Depends(require_permission("system.configure")),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    service = OrgService(session)
    return await service.update_organization(data)
