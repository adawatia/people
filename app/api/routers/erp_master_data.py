"""ERP-owned master-data upsert endpoints.

The public read APIs remain available to authenticated application users. All
master-data writes are isolated under this integration namespace and require a
scoped ERP client credential.

Bulk responses use the shared ``ErpBatchResult`` envelope: one correlation id,
summarised counts, and a per-item outcome with a stable error code and a
``retryable`` flag. Master-data upserts commit per record (matching the
single-record endpoints), so a rejected item never discards records already
accepted in the same page.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.erp_auth import ErpPrincipal, require_erp_scope
from core.erp_batch import (
    ErpBatchResult,
    apply_batch_status,
    classify_erp_error,
    log_erp_item_failure,
    new_batch,
    record_batch,
    resolve_batch_id,
)
from schemas import (
    DepartmentRead,
    OrganizationRead,
    OrganizationUpdate,
    UnitRead,
    UnitUpdate,
)
from schemas.designations import DesignationRead, DesignationUpdate
from schemas.erp_bulk import (
    ErpDepartmentBulkUpsert,
    ErpDesignationBulkUpsert,
    ErpUnitBulkUpsert,
)
from schemas.org import DepartmentUpsert
from services.designation_service import DesignationService
from services.org_service import OrgService

router = APIRouter(prefix="/integrations/erp")


class ErpIdentified(Protocol):
    erp_id: str


async def _apply_bulk[ItemT: ErpIdentified](
    items: list[ItemT],
    apply: Callable[[ItemT], Awaitable[int]],
    session: AsyncSession,
    result: ErpBatchResult,
) -> None:
    """Apply one item at a time and record a per-item outcome."""
    for item in items:
        erp_id = item.erp_id
        try:
            local_id = await apply(item)
            result.add_accepted(erp_id, local_id)
        except Exception as exc:
            # Master-data services commit per record, so a failure can leave the
            # session dirty; roll back before recording the next outcome.
            await session.rollback()
            log_erp_item_failure(erp_id, exc, result.batch_id, result.endpoint)
            code, message, retryable = classify_erp_error(exc)
            result.add_failure(erp_id, code=code, message=message, retryable=retryable)


async def _finish(
    session: AsyncSession,
    result: ErpBatchResult,
    response: Response,
    principal: ErpPrincipal,
    *,
    commit: bool = True,
) -> ErpBatchResult:
    apply_batch_status(response, result)
    await record_batch(session, result, client_id=principal.client_id, http_status=response.status_code)
    if commit:
        await session.commit()
    return result


@router.put(
    "/organization/{erp_id}",
    response_model=OrganizationRead,
    tags=["erp-organization"],
    summary="Idempotently upsert the ERP organization",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_organization(
    erp_id: str, data: OrganizationUpdate, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> OrganizationRead:
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
    "/units/bulk",
    response_model=ErpBatchResult,
    tags=["erp-units"],
    summary="Idempotently upsert multiple ERP units",
    description=(
        "Applies the same rules as the single unit upsert to a page of units. Each "
        "item is reported in the batch envelope; the organization must exist "
        "before units are synced."
    ),
)
async def upsert_units_bulk(
    response: Response,
    payload: ErpUnitBulkUpsert,
    batch_id: str = Depends(resolve_batch_id),
    principal: ErpPrincipal = Depends(require_erp_scope("master-data:write")),
    session: AsyncSession = Depends(get_async_session),
) -> ErpBatchResult:
    service = OrgService(session)
    result = new_batch("units.bulk", batch_id, len(payload.units))

    async def apply(item) -> int:
        fields = item.model_dump(exclude={"erp_id"}, exclude_unset=True)
        unit = await service.upsert_unit(item.erp_id, UnitUpdate(**fields))
        return unit.id

    await _apply_bulk(payload.units, apply, session, result)
    return await _finish(session, result, response, principal)


@router.put(
    "/departments/by-erp-id/{erp_id}",
    response_model=DepartmentRead,
    tags=["erp-departments"],
    summary="Idempotently upsert an ERP department",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_department(
    erp_id: str, data: DepartmentUpsert, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> DepartmentRead:
    return await OrgService(session).upsert_department(erp_id, data)


@router.put(
    "/departments/bulk",
    response_model=ErpBatchResult,
    tags=["erp-departments"],
    summary="Idempotently upsert multiple ERP departments",
    description=(
        "Applies the same rules as the single department upsert. Send units first: "
        "`unit_id` is the local unit id resolved from the unit upsert response."
    ),
)
async def upsert_departments_bulk(
    response: Response,
    payload: ErpDepartmentBulkUpsert,
    batch_id: str = Depends(resolve_batch_id),
    principal: ErpPrincipal = Depends(require_erp_scope("master-data:write")),
    session: AsyncSession = Depends(get_async_session),
) -> ErpBatchResult:
    service = OrgService(session)
    result = new_batch("departments.bulk", batch_id, len(payload.departments))

    async def apply(item) -> int:
        fields = item.model_dump(exclude={"erp_id"}, exclude_unset=True)
        department = await service.upsert_department(item.erp_id, DepartmentUpsert(**fields))
        return department.id

    await _apply_bulk(payload.departments, apply, session, result)
    return await _finish(session, result, response, principal)


@router.put(
    "/designations/by-erp-id/{erp_id}",
    response_model=DesignationRead,
    tags=["erp-designations"],
    summary="Idempotently upsert an ERP designation",
    dependencies=[Depends(require_erp_scope("master-data:write"))],
)
async def upsert_designation(
    erp_id: str, data: DesignationUpdate, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> DesignationRead:
    return DesignationRead.model_validate(await DesignationService(session).upsert_designation(erp_id, data))


@router.put(
    "/designations/bulk",
    response_model=ErpBatchResult,
    tags=["erp-designations"],
    summary="Idempotently upsert multiple ERP designations",
    description="Applies the same rules as the single designation upsert, with a per-item outcome.",
)
async def upsert_designations_bulk(
    response: Response,
    payload: ErpDesignationBulkUpsert,
    batch_id: str = Depends(resolve_batch_id),
    principal: ErpPrincipal = Depends(require_erp_scope("master-data:write")),
    session: AsyncSession = Depends(get_async_session),
) -> ErpBatchResult:
    service = DesignationService(session)
    result = new_batch("designations.bulk", batch_id, len(payload.designations))

    async def apply(item) -> int:
        fields = item.model_dump(exclude={"erp_id"}, exclude_unset=True)
        designation = await service.upsert_designation(item.erp_id, DesignationUpdate(**fields))
        return designation.id

    await _apply_bulk(payload.designations, apply, session, result)
    return await _finish(session, result, response, principal)
