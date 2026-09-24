from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.business_roles import resolve_business_access
from core.database import get_async_session
from core.employee_access import get_current_employee, get_employee_scope
from core.pagination import PaginatedResponse
from db.models import User
from schemas.shifts import (
    EmployeeShiftScheduleRead,
    ShiftAssignmentRead,
    ShiftRead,
)
from services.shift_service import ShiftService

router = APIRouter(prefix="/shifts", tags=["shifts"])


async def _employee_self_scope(user: User, session: AsyncSession):
    """Return the employee profile only for a plain employee login.

    Shift management remains available to elevated business roles (and Super
    Admin). An employee with no elevated role is intentionally limited to their
    own effective assignment because their schedule is displayed on the
    dashboard rather than in a management tab.
    """
    if user.is_superuser:
        return None
    employee = await get_current_employee(user, session)
    return employee if resolve_business_access(employee).business_role is None else None


async def _employee_visible_shifts(service: ShiftService, employee_id: int) -> list[ShiftRead]:
    """Return the shift definitions the employee works over the schedule horizon.

    A single repository query covers the assignment window (today through the
    upcoming-schedule horizon, including a night shift started yesterday), so
    no per-window service lookups — and no N+1 — are needed.
    """
    shifts = await service.repo.list_active_assignment_shifts(employee_id)
    return [ShiftRead.model_validate(shift) for shift in shifts]


@router.get("/", response_model=PaginatedResponse[ShiftRead])
async def list_shifts(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    unit_id: int | None = None,
    is_active: bool | None = True,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[ShiftRead]:
    service = ShiftService(session)
    employee = await _employee_self_scope(user, session)
    return await service.definitions_page(
        employee_id=employee.id if employee else None,
        unit_id=unit_id,
        is_active=is_active,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/assignments", response_model=PaginatedResponse[ShiftAssignmentRead])
async def list_shift_assignments(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    shift_id: int | None = None,
    employee_id: int | None = None,
    status: str | None = None,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[ShiftAssignmentRead]:
    service = ShiftService(session)
    scope = await get_employee_scope(user, session)
    return await service.assignments_page(scope, page=page, page_size=page_size, search=search,
        sort_by=sort_by, sort_order=sort_order, shift_id=shift_id, employee_id=employee_id, status=status)


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
    target = await service.employee_repo.get_by_id(assignment.employee_id)
    if target is None or not (await get_employee_scope(user, session)).allows(target):
        raise HTTPException(403, "You do not have access to this shift assignment")
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
    target = await service.employee_repo.get_by_id(emp_id)
    if target is None:
        raise HTTPException(404, "Employee not found")
    if not (await get_employee_scope(user, session)).allows(target):
        raise HTTPException(403, "You do not have access to this shift schedule")
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
        visible_shifts = await _employee_visible_shifts(service, employee.id)
        if shift_id not in {shift.id for shift in visible_shifts}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this shift")
    shift = await service.get_shift(shift_id)
    return ShiftRead.model_validate(shift)
