"""ERP-owned master-data upsert endpoints.
The public read APIs remain available to authenticated application users. All
master-data writes are isolated under this integration namespace and require
a scoped ERP client credential.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.erp_auth import require_erp_scope
from schemas import (
    DepartmentRead,
    OrganizationRead,
    OrganizationUpdate,
    UnitRead,
    UnitUpdate,
)
from schemas.designations import DesignationRead, DesignationUpdate
from schemas.org import DepartmentUpsert
from services.designation_service import DesignationService
from services.org_service import OrgService

router = APIRouter(prefix="/integrations/erp")


@router.put(
    "/organization/{erp_id}",
    response_model=OrganizationRead,
    tags=["erp-organization"],
    summary="Idempotently upsert the ERP organization",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_organization(
    erp_id: str, data: OrganizationUpdate, session: AsyncSession = Depends(get_async_session)
):
    return await OrgService(session).upsert_organization(erp_id, data)


@router.put(
    "/units/by-erp-id/{erp_id}",
    response_model=UnitRead,
    tags=["erp-units"],
    summary="Idempotently upsert an ERP unit",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_unit(erp_id: str, data: UnitUpdate, session: AsyncSession = Depends(get_async_session)):
    return await OrgService(session).upsert_unit(erp_id, data)


@router.put(
    "/departments/by-erp-id/{erp_id}",
    response_model=DepartmentRead,
    tags=["erp-departments"],
    summary="Idempotently upsert an ERP department",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_department(erp_id: str, data: DepartmentUpsert, session: AsyncSession = Depends(get_async_session)):
    return await OrgService(session).upsert_department(erp_id, data)


@router.put(
    "/designations/by-erp-id/{erp_id}",
    response_model=DesignationRead,
    tags=["erp-designations"],
    summary="Idempotently upsert an ERP designation",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_designation(erp_id: str, data: DesignationUpdate, session: AsyncSession = Depends(get_async_session)):
    return DesignationRead.model_validate(await DesignationService(session).upsert_designation(erp_id, data))
