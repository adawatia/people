"""ERP-owned shift and employee shift-assignment synchronization."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.erp_auth import require_erp_scope
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
async def upsert_shift(erp_id: str, data: ShiftUpsert, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).upsert_shift(erp_id, data)


@router.post(
    "/assignments",
    response_model=ShiftAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="ERP assign employee shift",
    dependencies=[Depends(require_erp_scope("shifts:write"))],
)
async def assign_shift(data: ShiftAssignmentCreate, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).assign_shift(data)


@router.post(
    "/assignments/bulk",
    response_model=list[ShiftAssignmentRead],
    status_code=status.HTTP_201_CREATED,
    summary="ERP bulk assign shifts",
    dependencies=[Depends(require_erp_scope("shifts:write"))],
)
async def bulk_assign_shifts(data: BulkShiftAssignmentCreate, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).bulk_assign_shifts(data)


@router.patch(
    "/assignments/{assignment_id}/cancel",
    response_model=ShiftAssignmentRead,
    summary="ERP cancel shift assignment",
    dependencies=[Depends(require_erp_scope("shifts:write"))],
)
async def cancel_shift_assignment(assignment_id: int, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).cancel_assignment(assignment_id)
