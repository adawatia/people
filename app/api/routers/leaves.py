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
from core.pagination import PaginatedResponse
from db.models import LeavePeriod, LeaveType, User
from schemas.leaves import (
    LeaveApplicationAction,
    LeaveApplicationCreate,
    LeaveApplicationRead,
    LeaveBalanceRead,
    LeaveCancellationAction,
    LeaveCancellationRequest,
    LeavePeriodCreate,
    LeavePeriodRead,
    LeaveTypeCreate,
    LeaveTypeRead,
    LeaveTypeUpdate,
)
from services.leave_service import LeaveService
from services.lookup_service import LookupService

router = APIRouter(prefix="/leaves", tags=["leaves"])

LEAVE_MANAGEMENT_PERMISSIONS = ("leave.manage", "leave.approve", "leave.reject")


async def _leave_management_scope(user: User, session: AsyncSession) -> EmployeeAccessScope:
    scope = EmployeeAccessScope()
    for permission in LEAVE_MANAGEMENT_PERMISSIONS:
        scope.include(await get_permission_scope(user, permission, session))
    return scope


# ── Leave Periods ─────────────────────────────────────────────────────────────

@router.get("/periods", response_model=PaginatedResponse[LeavePeriodRead])
async def list_leave_periods(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[LeavePeriodRead]:
    return await LookupService(session).list_page(
        LeavePeriod,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters={},
    )


@router.post(
    "/periods",
    response_model=LeavePeriodRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_erp_api_key)],
    tags=["erp-leaves"],
    summary="ERP create leave period",
    description="ERP-only leave-period master-data sync. Requires the X-API-Key header.",
)
async def create_leave_period(
    data: LeavePeriodCreate,
    session: AsyncSession = Depends(get_async_session),
) -> LeavePeriodRead:
    service = LeaveService(session)
    return await service.create_period(data)


# ── Leave Types ───────────────────────────────────────────────────────────────

@router.get("/types", response_model=PaginatedResponse[LeaveTypeRead])
async def list_leave_types(
    is_active: bool | None = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[LeaveTypeRead]:
    return await LookupService(session).list_page(
        LeaveType,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters={"is_active": is_active},
    )


@router.post(
    "/types",
    response_model=LeaveTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_erp_api_key)],
    tags=["erp-leaves"],
    summary="ERP create leave type",
    description="ERP-only leave-type master-data sync. Requires the X-API-Key header.",
)
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


@router.patch(
    "/types/{type_id}",
    response_model=LeaveTypeRead,
    dependencies=[Depends(verify_erp_api_key)],
    tags=["erp-leaves"],
    summary="ERP update leave type",
    description="ERP-only leave-type master-data update. Requires the X-API-Key header.",
)
async def update_leave_type(
    type_id: int,
    data: LeaveTypeUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> LeaveTypeRead:
    service = LeaveService(session)
    return await service.update_type(type_id, data)


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
    # Employees may read their own ERP-synchronized balance with leave.apply;
    # leave.manage remains reserved for HR-level management access.
    await require_employee_access(current_user, employee, "leave.apply", session, allow_self=True)
    return await service.get_employee_leave_balances(emp_id, for_date=for_date)


# ── Leave Applications ────────────────────────────────────────────────────────

@router.get("/", response_model=PaginatedResponse[LeaveApplicationRead])
async def list_leave_applications(
    employee_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    from_date: date | None = None,
    to_date: date | None = None,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[LeaveApplicationRead]:
    service = LeaveService(session)
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
    elif scope.self_only:
        employee_id = (await get_current_employee(current_user, session)).id
    return await service.list_applications_page(
        page=page, page_size=page_size,
        search=search, sort_by=sort_by, sort_order=sort_order,
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
    # Applying leave is a self-service employee capability.
    await require_employee_access(current_user, employee, "leave.apply", session, allow_self=True)
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
    request: LeaveCancellationRequest | None = None,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveApplicationRead:
    service = LeaveService(session)
    application = await service.repo.get_application_by_id(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Leave application not found")
    await require_employee_access(current_user, application.employee, "leave.cancel", session, allow_self=True)
    return await service.request_leave_cancellation(
        app_id,
        current_user.id,
        request.effective_date if request else None,
        request.reason if request else None,
    )


@router.patch("/{app_id}/cancellation/approve", response_model=LeaveApplicationRead)
async def approve_leave_cancellation(
    app_id: int,
    current_user: User = Depends(require_permission("leave.approve")),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveApplicationRead:
    service = LeaveService(session)
    application = await service.repo.get_application_by_id(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Leave application not found")
    await require_employee_access(current_user, application.employee, "leave.approve", session)
    return await service.approve_leave_cancellation(app_id, current_user.id)


@router.patch("/{app_id}/cancellation/reject", response_model=LeaveApplicationRead)
async def reject_leave_cancellation(
    app_id: int,
    action: LeaveCancellationAction,
    current_user: User = Depends(require_permission("leave.reject")),
    session: AsyncSession = Depends(get_async_session),
) -> LeaveApplicationRead:
    service = LeaveService(session)
    application = await service.repo.get_application_by_id(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Leave application not found")
    await require_employee_access(current_user, application.employee, "leave.reject", session)
    return await service.reject_leave_cancellation(app_id, current_user.id, action.rejection_reason)
