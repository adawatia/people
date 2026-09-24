"""ERP-owned shift and employee shift-assignment synchronization."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_erp_api_key
from core.database import get_async_session
from schemas.shifts import (
    BulkShiftAssignmentCreate,
    ShiftAssignmentCreate,
    ShiftAssignmentRead,
    ShiftCreate,
    ShiftRead,
    ShiftUpdate,
)
from services.shift_service import ShiftService

router = APIRouter(prefix="/integrations/erp/shifts", tags=["erp-shifts"])


@router.post("", response_model=ShiftRead, status_code=status.HTTP_201_CREATED, summary="ERP create shift", dependencies=[Depends(verify_erp_api_key)])
async def create_shift(data: ShiftCreate, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).create_shift(data)


@router.patch("/{shift_id}", response_model=ShiftRead, summary="ERP update shift", dependencies=[Depends(verify_erp_api_key)])
async def update_shift(shift_id: int, data: ShiftUpdate, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).update_shift(shift_id, data)


@router.post("/assignments", response_model=ShiftAssignmentRead, status_code=status.HTTP_201_CREATED, summary="ERP assign employee shift", dependencies=[Depends(verify_erp_api_key)])
async def assign_shift(data: ShiftAssignmentCreate, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).assign_shift(data)


@router.post("/assignments/bulk", response_model=list[ShiftAssignmentRead], status_code=status.HTTP_201_CREATED, summary="ERP bulk assign shifts", dependencies=[Depends(verify_erp_api_key)])
async def bulk_assign_shifts(data: BulkShiftAssignmentCreate, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).bulk_assign_shifts(data)


@router.patch("/assignments/{assignment_id}/cancel", response_model=ShiftAssignmentRead, summary="ERP cancel shift assignment", dependencies=[Depends(verify_erp_api_key)])
async def cancel_shift_assignment(assignment_id: int, session: AsyncSession = Depends(get_async_session)):
    return await ShiftService(session).cancel_assignment(assignment_id)
