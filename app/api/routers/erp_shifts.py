"""ERP-owned shift and employee shift-assignment synchronization."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
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
from schemas.shifts import (
    BulkShiftAssignmentCreate,
    ShiftAssignmentCreate,
    ShiftAssignmentRead,
    ShiftRead,
    ShiftUpsert,
)
from services.shift_service import ShiftService

router = APIRouter(prefix="/integrations/erp/shifts", tags=["erp-shifts"])


@router.put(
    "/by-erp-id/{erp_id}",
    response_model=ShiftRead,
    summary="Idempotently upsert an ERP shift",
    dependencies=[Depends(require_erp_scope("shifts:write"))],
)
async def upsert_shift(
    erp_id: str, data: ShiftUpsert, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> ShiftRead:
    return await ShiftService(session).upsert_shift(erp_id, data)


@router.post(
    "/assignments",
    response_model=ShiftAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="ERP assign employee shift",
    dependencies=[Depends(require_erp_scope("shifts:write"))],
)
async def assign_shift(
    data: ShiftAssignmentCreate, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> ShiftAssignmentRead:
    return await ShiftService(session).assign_shift(data)


@router.post(
    "/assignments/bulk",
    response_model=ErpBatchResult,
    summary="ERP bulk assign shifts",
    description=(
        "Assigns one shift to many employees. Request-level problems (unknown "
        "shift, inconsistent unit/department, unresolved employee ids) reject the "
        "whole request; each employee is otherwise isolated so one ineligible "
        "employee does not block the rest. Existing overlapping assignments are "
        "closed, not rejected. Keys are employee ids."
    ),
)
async def bulk_assign_shifts(
    response: Response,
    data: BulkShiftAssignmentCreate,
    batch_id: Annotated[str, Depends(resolve_batch_id)],
    principal: Annotated[ErpPrincipal, Depends(require_erp_scope("shifts:write"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ErpBatchResult:
    service = ShiftService(session)
    # Request-level validation first: if the shift itself is unusable, no item
    # can succeed, and a 4xx is more truthful than a page of failures.
    shift, employees = await service.resolve_bulk_assignment_targets(data)
    result = new_batch("shifts.assignments.bulk", batch_id, len(employees))
    for employee in employees:
        try:
            async with session.begin_nested():
                assignment = await service.stage_bulk_assignment(employee, shift, data, None)
            result.add_accepted(str(employee.id), assignment.id)
        except Exception as exc:
            log_erp_item_failure(str(employee.id), exc, result.batch_id, result.endpoint)
            code, message, retryable = classify_erp_error(exc)
            result.add_failure(str(employee.id), code=code, message=message, retryable=retryable)
    apply_batch_status(response, result)
    await record_batch(session, result, client_id=principal.client_id, http_status=response.status_code)
    await session.commit()
    return result


@router.patch(
    "/assignments/{assignment_id}/cancel",
    response_model=ShiftAssignmentRead,
    summary="ERP cancel shift assignment",
    dependencies=[Depends(require_erp_scope("shifts:write"))],
)
async def cancel_shift_assignment(
    assignment_id: int, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> ShiftAssignmentRead:
    return await ShiftService(session).cancel_assignment(assignment_id)
