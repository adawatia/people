from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from db.models import User
from schemas.shifts import (
    EmployeeShiftScheduleRead,
    ShiftAssignmentRead,
    ShiftRead,
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


@router.get("/employee/{emp_id}/schedule", response_model=EmployeeShiftScheduleRead)
async def get_employee_shift_schedule(
    emp_id: int,
    for_timestamp: datetime | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeShiftScheduleRead:
    service = ShiftService(session)
    return await service.get_employee_shift_schedule(emp_id, for_timestamp=for_timestamp)


@router.get("/{shift_id}", response_model=ShiftRead)
async def get_shift(
    shift_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftRead:
    service = ShiftService(session)
    shift = await service.get_shift(shift_id)
    return ShiftRead.model_validate(shift)
