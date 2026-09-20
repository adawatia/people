from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission, verify_erp_api_key
from core.database import get_async_session
from core.employee_access import (
    EmployeeAccessScope,
    get_current_employee,
    get_permission_scope,
    require_employee_access,
)
from db.models import User
from schemas.leaves import (
    LeaveAllocationCreate,
    LeaveAllocationRead,
    LeaveApplicationAction,
    LeaveApplicationCreate,
    LeaveApplicationRead,
    LeaveBalanceRead,
    LeavePeriodCreate,
    LeavePeriodRead,
    LeaveTypeCreate,
    LeaveTypeRead,
    LeaveTypeUpdate,
)
from services.leave_service import LeaveService

router = APIRouter(prefix="/leaves", tags=["leaves"])

LEAVE_MANAGEMENT_PERMISSIONS = ("leave.manage", "leave.approve", "leave.reject")


async def _leave_management_scope(user: User, session: AsyncSession) -> EmployeeAccessScope:
    scope = EmployeeAccessScope()
    for permission in LEAVE_MANAGEMENT_PERMISSIONS:
        scope.include(await get_permission_scope(user, permission, session))
    return scope


# ── Leave Periods ─────────────────────────────────────────────────────────────

@router.get("/periods", response_model=list[LeavePeriodRead])
async def list_leave_periods(
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[LeavePeriodRead]:
    service = LeaveService(session)
    return await service.list_periods()


@router.post("/periods", response_model=LeavePeriodRead, status_code=status.HTTP_201_CREATED, include_in_schema=False, dependencies=[Depends(verify_erp_api_key)])
async def create_leave_period(
    data: LeavePeriodCreate,
    session: AsyncSession = Depends(get_async_session),
) -> LeavePeriodRead:
    service = LeaveService(session)
    return await service.create_period(data)


# ── Leave Types ───────────────────────────────────────────────────────────────

@router.get("/types", response_model=list[LeaveTypeRead])
async def list_leave_types(
    is_active: bool | None = Query(True),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[LeaveTypeRead]:
    service = LeaveService(session)
    return await service.list_types(is_active=is_active)


@router.post("/types", response_model=LeaveTypeRead, status_code=status.HTTP_201_CREATED, include_in_schema=False, dependencies=[Depends(verify_erp_api_key)])
async def create_leave_type(
    data: LeaveTypeCreate,
    session: AsyncSession = Depends(get_async_session),
) -> LeaveTypeRead:
    service = LeaveService(session)
    return await service.create_type(data)


@router.get("/types/{type_id}", response_model=LeaveTypeRead)
async def get_leave_type(
    type_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveTypeRead:
    service = LeaveService(session)
    lt = await service.get_type(type_id)
    return LeaveTypeRead.model_validate(lt)


@router.patch("/types/{type_id}", response_model=LeaveTypeRead, include_in_schema=False, dependencies=[Depends(verify_erp_api_key)])
async def update_leave_type(
    type_id: int,
    data: LeaveTypeUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> LeaveTypeRead:
    service = LeaveService(session)
    return await service.update_type(type_id, data)


# ── Leave Allocations ─────────────────────────────────────────────────────────

@router.get("/allocations", response_model=list[LeaveAllocationRead])
async def list_leave_allocations(
    employee_id: int | None = None,
    leave_period_id: int | None = None,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[LeaveAllocationRead]:
    service = LeaveService(session)
    current_employee = await get_current_employee(current_user, session)
    scope = await get_permission_scope(current_user, "leave.manage", session)
    if employee_id is None:
        if not scope.organization and not scope.unit_ids and not scope.department_ids:
            employee_id = current_employee.id
    else:
        employee = await service.employee_repo.get_by_id(employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        await require_employee_access(current_user, employee, "leave.manage", session, allow_self=True)
    return await service.list_allocations(
        employee_id=employee_id,
        leave_period_id=leave_period_id,
        unit_ids=None if scope.organization else scope.unit_ids,
        department_ids=None if scope.organization else scope.department_ids,
    )


@router.post("/allocations", response_model=LeaveAllocationRead, status_code=status.HTTP_201_CREATED)
async def allocate_leaves(
    data: LeaveAllocationCreate,
    current_user: User = Depends(require_permission("leave.manage")),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveAllocationRead:
    service = LeaveService(session)
    employee = await service.employee_repo.get_by_id(data.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(current_user, employee, "leave.manage", session)
    return await service.allocate_leaves(data)


# ── Leave Balances ────────────────────────────────────────────────────────────

@router.get("/balance/employee/{emp_id}", response_model=list[LeaveBalanceRead])
async def get_leave_balance(
    emp_id: int,
    for_date: date | None = Query(None),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[LeaveBalanceRead]:
    service = LeaveService(session)
    employee = await service.employee_repo.get_by_id(emp_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(current_user, employee, "leave.manage", session, allow_self=True)
    return await service.get_employee_leave_balances(emp_id, for_date=for_date)


# ── Leave Applications ────────────────────────────────────────────────────────

@router.get("/", response_model=list[LeaveApplicationRead])
async def list_leave_applications(
    employee_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[LeaveApplicationRead]:
    service = LeaveService(session)
    current_employee = await get_current_employee(current_user, session)
    scope = await _leave_management_scope(current_user, session)
    if employee_id is not None:
        employee = await service.employee_repo.get_by_id(employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        await require_employee_access(
            current_user,
            employee,
            LEAVE_MANAGEMENT_PERMISSIONS,
            session,
            allow_self=True,
        )
    elif not scope.organization and not scope.unit_ids and not scope.department_ids:
        employee_id = current_employee.id
    return await service.list_applications(
        employee_id=employee_id,
        status=status_filter,
        from_date=from_date,
        to_date=to_date,
        unit_ids=None if scope.organization else scope.unit_ids,
        department_ids=None if scope.organization else scope.department_ids,
    )


@router.get("/{app_id}", response_model=LeaveApplicationRead)
async def get_leave_application(
    app_id: int,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveApplicationRead:
    service = LeaveService(session)
    application = await service.repo.get_application_by_id(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Leave application not found")
    await require_employee_access(
        current_user,
        application.employee,
        LEAVE_MANAGEMENT_PERMISSIONS,
        session,
        allow_self=True,
    )
    return await service.get_application(app_id)


@router.post("/", response_model=LeaveApplicationRead, status_code=status.HTTP_201_CREATED)
async def apply_leave(
    data: LeaveApplicationCreate,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveApplicationRead:
    service = LeaveService(session)
    employee = await service.employee_repo.get_by_id(data.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(current_user, employee, "leave.manage", session, allow_self=True)
    return await service.apply_leave(data)


@router.patch("/{app_id}/approve", response_model=LeaveApplicationRead)
async def approve_leave(
    app_id: int,
    current_user: User = Depends(require_permission("leave.approve")),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveApplicationRead:
    service = LeaveService(session)
    application = await service.repo.get_application_by_id(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Leave application not found")
    await require_employee_access(current_user, application.employee, "leave.approve", session)
    return await service.approve_leave(app_id, current_user.id)


@router.patch("/{app_id}/reject", response_model=LeaveApplicationRead)
async def reject_leave(
    app_id: int,
    action: LeaveApplicationAction,
    current_user: User = Depends(require_permission("leave.reject")),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveApplicationRead:
    service = LeaveService(session)
    application = await service.repo.get_application_by_id(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Leave application not found")
    await require_employee_access(current_user, application.employee, "leave.reject", session)
    return await service.reject_leave(app_id, current_user.id, action.rejection_reason)


@router.patch("/{app_id}/cancel", response_model=LeaveApplicationRead)
async def cancel_leave(
    app_id: int,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveApplicationRead:
    service = LeaveService(session)
    application = await service.repo.get_application_by_id(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Leave application not found")
    await require_employee_access(current_user, application.employee, "leave.cancel", session, allow_self=True)
    return await service.cancel_leave(app_id, current_user.id)
