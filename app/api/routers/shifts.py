from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas.shifts import (
    BulkShiftAssignmentCreate,
    EmployeeShiftScheduleRead,
    ShiftAssignmentCreate,
    ShiftAssignmentRead,
    ShiftCreate,
    ShiftRead,
    ShiftUpdate,
)
from services.shift_service import ShiftService

router = APIRouter(prefix="/shifts", tags=["shifts"])


@router.get("/", response_model=list[ShiftRead])
async def list_shifts(
    unit_id: int | None = None,
    is_active: bool | None = True,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[ShiftRead]:
    service = ShiftService(session)
    return await service.list_shifts(unit_id=unit_id, is_active=is_active)


@router.get("/{shift_id}", response_model=ShiftRead)
async def get_shift(
    shift_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftRead:
    service = ShiftService(session)
    shift = await service.get_shift(shift_id)
    return ShiftRead.model_validate(shift)


@router.post("/", response_model=ShiftRead, status_code=status.HTTP_201_CREATED)
async def create_shift(
    data: ShiftCreate,
    _: User = Depends(require_permission("shift.assign")),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftRead:
    service = ShiftService(session)
    return await service.create_shift(data)


@router.patch("/{shift_id}", response_model=ShiftRead)
async def update_shift(
    shift_id: int,
    data: ShiftUpdate,
    _: User = Depends(require_permission("shift.update")),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftRead:
    service = ShiftService(session)
    return await service.update_shift(shift_id, data)


@router.post("/assignments", response_model=ShiftAssignmentRead, status_code=status.HTTP_201_CREATED)
async def assign_shift(
    data: ShiftAssignmentCreate,
    current_user: User = Depends(require_permission("shift.assign")),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftAssignmentRead:
    service = ShiftService(session)
    return await service.assign_shift(data, assigned_by_user_id=current_user.id)


@router.post("/assignments/bulk", response_model=list[ShiftAssignmentRead], status_code=status.HTTP_201_CREATED)
async def bulk_assign_shifts(
    data: BulkShiftAssignmentCreate,
    current_user: User = Depends(require_permission("shift.assign")),
    session: AsyncSession = Depends(get_async_session),
) -> list[ShiftAssignmentRead]:
    service = ShiftService(session)
    return await service.bulk_assign_shifts(data, assigned_by_user_id=current_user.id)


@router.get("/assignments", response_model=list[ShiftAssignmentRead])
async def list_shift_assignments(
    shift_id: int | None = None,
    employee_id: int | None = None,
    status: str | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[ShiftAssignmentRead]:
    service = ShiftService(session)
    return await service.list_assignments(shift_id=shift_id, employee_id=employee_id, status=status)


@router.get("/assignments/{assignment_id}", response_model=ShiftAssignmentRead)
async def get_shift_assignment(
    assignment_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftAssignmentRead:
    service = ShiftService(session)
    return await service.get_assignment(assignment_id)


@router.patch("/assignments/{assignment_id}/cancel", response_model=ShiftAssignmentRead)
async def cancel_shift_assignment(
    assignment_id: int,
    current_user: User = Depends(require_permission("shift.assign")),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftAssignmentRead:
    service = ShiftService(session)
    return await service.cancel_assignment(assignment_id, cancelled_by_user_id=current_user.id)


@router.get("/employee/{emp_id}/schedule", response_model=EmployeeShiftScheduleRead)
async def get_employee_shift_schedule(
    emp_id: int,
    for_timestamp: datetime | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeShiftScheduleRead:
    service = ShiftService(session)
    return await service.get_employee_shift_schedule(emp_id, for_timestamp=for_timestamp)
