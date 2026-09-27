from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import current_business_user
from core.database import get_async_session
from db.models import User
from schemas import OrganizationRead
from services.org_service import OrgService

router = APIRouter(prefix="/org/organization", tags=["organization"])


@router.get("", response_model=OrganizationRead)
async def get_organization(
    _: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    service = OrgService(session)
    return await service.get_organization()
