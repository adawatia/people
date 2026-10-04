"""ERP-owned master-data CRUD endpoints.
The public read APIs remain available to authenticated application users. All
master-data writes are isolated under this integration namespace and require
a scoped ERP client credential.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.erp_auth import require_erp_scope
from schemas import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    OrganizationRead,
    OrganizationUpdate,
    UnitCreate,
    UnitRead,
    UnitUpdate,
)
from schemas.designations import DesignationCreate, DesignationRead, DesignationUpdate
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
    from schemas.org import OrganizationCreate

    existing = await OrgService(session).repo.get_organization()
    merged = data.model_dump(exclude_unset=True)
    if existing:
        baseline = OrganizationRead.model_validate(existing).model_dump(
            exclude={"id", "erp_id", "created_at", "updated_at"}
        )
        merged = {**baseline, **merged}
    if not merged.get("name"):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="name is required when creating the organization")
    return await OrgService(session).upsert_organization(erp_id, OrganizationCreate(**merged))


@router.put(
    "/units/by-erp-id/{erp_id}",
    response_model=UnitRead,
    tags=["erp-units"],
    summary="Idempotently upsert an ERP unit",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_unit(erp_id: str, data: UnitCreate, session: AsyncSession = Depends(get_async_session)):
    return await OrgService(session).upsert_unit(erp_id, data)


@router.put(
    "/departments/by-erp-id/{erp_id}",
    response_model=DepartmentRead,
    tags=["erp-departments"],
    summary="Idempotently upsert an ERP department",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_department(erp_id: str, data: DepartmentCreate, session: AsyncSession = Depends(get_async_session)):
    return await OrgService(session).upsert_department(erp_id, data)


@router.put(
    "/designations/by-erp-id/{erp_id}",
    response_model=DesignationRead,
    tags=["erp-designations"],
    summary="Idempotently upsert an ERP designation",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_designation(erp_id: str, data: DesignationCreate, session: AsyncSession = Depends(get_async_session)):
    return DesignationRead.model_validate(await DesignationService(session).upsert_designation(erp_id, data))


@router.post(
    "/units",
    response_model=UnitRead,
    tags=["erp-units"],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def create_unit(data: UnitCreate, session: AsyncSession = Depends(get_async_session)):
    return await OrgService(session).create_unit(data)


@router.patch(
    "/units/{unit_id}",
    response_model=UnitRead,
    tags=["erp-units"],
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def update_unit(unit_id: int, data: UnitUpdate, session: AsyncSession = Depends(get_async_session)):
    return await OrgService(session).update_unit(unit_id, data)


@router.delete(
    "/units/{unit_id}",
    tags=["erp-units"],
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def delete_unit(unit_id: int, session: AsyncSession = Depends(get_async_session)):
    await OrgService(session).delete_unit(unit_id)


@router.post(
    "/departments",
    response_model=DepartmentRead,
    tags=["erp-departments"],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def create_department(data: DepartmentCreate, session: AsyncSession = Depends(get_async_session)):
    return await OrgService(session).create_department(data)


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentRead,
    tags=["erp-departments"],
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def update_department(
    department_id: int, data: DepartmentUpdate, session: AsyncSession = Depends(get_async_session)
):
    return await OrgService(session).update_department(department_id, data)


@router.delete(
    "/departments/{department_id}",
    tags=["erp-departments"],
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def delete_department(department_id: int, session: AsyncSession = Depends(get_async_session)):
    await OrgService(session).delete_department(department_id)


@router.post(
    "/designations",
    response_model=DesignationRead,
    tags=["erp-designations"],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def create_designation(data: DesignationCreate, session: AsyncSession = Depends(get_async_session)):
    return DesignationRead.model_validate(await DesignationService(session).create_designation(data))


@router.patch(
    "/designations/{designation_id}",
    response_model=DesignationRead,
    tags=["erp-designations"],
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def update_designation(
    designation_id: int, data: DesignationUpdate, session: AsyncSession = Depends(get_async_session)
):
    return DesignationRead.model_validate(await DesignationService(session).update_designation(designation_id, data))


@router.delete(
    "/designations/{designation_id}",
    tags=["erp-designations"],
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def delete_designation(designation_id: int, session: AsyncSession = Depends(get_async_session)):
    await DesignationService(session).delete_designation(designation_id)
