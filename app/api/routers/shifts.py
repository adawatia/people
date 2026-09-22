from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from core.employee_access import get_current_employee
from db.models import User, now_ist
from schemas.shifts import (
    EmployeeShiftScheduleRead,
    ShiftAssignmentRead,
    ShiftRead,
)
from services.shift_service import ShiftService

router = APIRouter(prefix="/shifts", tags=["shifts"])


async def _employee_self_scope(user: User, session: AsyncSession):
    """Return the employee profile only for an individual employee login.

    Shift management remains available to HR. Individual employees are
    intentionally limited to their own effective assignment because their
    schedule is displayed on the dashboard rather than in a management tab.
    """
    if user.is_superuser:
        return None
    employee = await get_current_employee(user, session)
    return employee if employee.role == "EMPLOYEE" else None


async def _employee_visible_shift_ids(service: ShiftService, employee_id: int) -> set[int]:
    """Return only the employee's assigned, active, and next shift definitions."""
    assigned = await service.get_shift_window_for_date(employee_id, now_ist().date())
    schedule = await service.get_employee_shift_schedule(employee_id, now_ist())
    windows = (assigned, schedule.current_shift, schedule.upcoming_shift)
    return {window.shift_id for window in windows if window is not None}


@router.get("/", response_model=list[ShiftRead])
async def list_shifts(
    unit_id: int | None = None,
    is_active: bool | None = True,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[ShiftRead]:
    service = ShiftService(session)
    employee = await _employee_self_scope(user, session)
    if employee:
        shift_ids = await _employee_visible_shift_ids(service, employee.id)
        return [ShiftRead.model_validate(await service.get_shift(shift_id)) for shift_id in sorted(shift_ids)]
    return await service.list_shifts(unit_id=unit_id, is_active=is_active)


@router.get("/assignments", response_model=list[ShiftAssignmentRead])
async def list_shift_assignments(
    shift_id: int | None = None,
    employee_id: int | None = None,
    status: str | None = None,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[ShiftAssignmentRead]:
    service = ShiftService(session)
    employee = await _employee_self_scope(user, session)
    if employee:
        employee_id = employee.id
    return await service.list_assignments(shift_id=shift_id, employee_id=employee_id, status=status)


@router.get("/assignments/{assignment_id}", response_model=ShiftAssignmentRead)
async def get_shift_assignment(
    assignment_id: int,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftAssignmentRead:
    service = ShiftService(session)
    assignment = await service.get_assignment(assignment_id)
    employee = await _employee_self_scope(user, session)
    if employee and assignment.employee_id != employee.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this shift assignment")
    return assignment


@router.get("/employee/{emp_id}/schedule", response_model=EmployeeShiftScheduleRead)
async def get_employee_shift_schedule(
    emp_id: int,
    for_timestamp: datetime | None = None,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeShiftScheduleRead:
    service = ShiftService(session)
    employee = await _employee_self_scope(user, session)
    if employee and emp_id != employee.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view your own shift schedule")
    return await service.get_employee_shift_schedule(emp_id, for_timestamp=for_timestamp)


@router.get("/{shift_id}", response_model=ShiftRead)
async def get_shift(
    shift_id: int,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> ShiftRead:
    service = ShiftService(session)
    employee = await _employee_self_scope(user, session)
    if employee:
        if shift_id not in await _employee_visible_shift_ids(service, employee.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this shift")
    shift = await service.get_shift(shift_id)
    return ShiftRead.model_validate(shift)
