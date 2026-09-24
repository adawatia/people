from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi_users import exceptions as fu_exceptions
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import UserManager, fastapi_users, get_user_manager, require_permission
from core.database import get_async_session
from core.employee_access import get_employee_scope, require_employee_access
from core.pagination import PaginatedResponse
from db.models import User
from schemas.employees import (
    EmployeeCreate,
    EmployeeDirectoryRead,
    EmployeeOnboardingCreate,
    EmployeeRead,
    EmployeeWorkHistoryRead,
    PaginatedEmployeesResponse,
)
from services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/", response_model=PaginatedEmployeesResponse)
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    q: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    unit_id: int | None = None,
    department_id: int | None = None,
    designation_id: int | None = None,
    status: str | None = None,
    reporting_manager_id: int | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedEmployeesResponse:
    current_user = _
    allowed_employee_ids: set[int] | None = None
    allowed_unit_ids: set[int] | None = None
    allowed_department_ids: set[int] | None = None
    if not current_user.is_superuser:
        # The directory is readable by any authenticated user, but only within
        # the row scope of their business role: an employee sees themselves, a
        # manager their department, HR their unit or the organization.
        scope = await get_employee_scope(current_user, session)
        if scope.organization:
            pass
        elif scope.employee_ids:
            allowed_employee_ids = set(scope.employee_ids)
        elif scope.unit_ids:
            allowed_unit_ids = scope.unit_ids
        elif scope.department_ids:
            allowed_department_ids = scope.department_ids
        else:
            # Elevated role without a usable scope (e.g. unit HR with no unit)
            # must not degrade into an unrestricted listing.
            allowed_employee_ids = set()
    service = EmployeeService(session)
    return await service.list_employees(
        page=page,
        page_size=page_size,
        q=search if search is not None else q, sort_by=sort_by, sort_order=sort_order,
        unit_id=unit_id,
        department_id=department_id,
        designation_id=designation_id,
        status_filter=status,
        reporting_manager_id=reporting_manager_id,
        allowed_employee_ids=allowed_employee_ids,
        allowed_unit_ids=allowed_unit_ids,
        allowed_department_ids=allowed_department_ids,
    )


@router.post(
    "/onboard",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Legacy employee onboarding (ERP-only replacement)",
    description="Visible for development testing. Returns 410 because employee provisioning is handled by the ERP integration.",
)
async def onboard_employee(
    data: EmployeeOnboardingCreate,
    _: User = Depends(require_permission("employee.create")),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeDirectoryRead:
    """Disabled: employee and account provisioning is ERP-owned."""
    raise HTTPException(status_code=410, detail="Employee provisioning is ERP-only; use /integrations/erp/employees")
    # Kept below temporarily for source compatibility while clients migrate.
    current_user = _
    user_id = data.user_id
    created_user = None
    try:
        if not data.create_user_account:
            raise HTTPException(status_code=400, detail="Every employee must have a linked login account")
        email = data.official_email or f"{data.username or data.employee_code}@invalid.local"
        if not data.phone_number:
            raise HTTPException(status_code=400, detail="Mobile number is required for an employee login")
        if not data.initial_password:
            raise HTTPException(status_code=400, detail="Provide an initial password for the employee login")
        username = data.username or email.split("@", 1)[0]
        username = username.lower().replace(" ", ".")
        existing_user = await session.scalar(select(User).where((User.username == username) | (User.email == email)))
        if existing_user:
            conflict = "username" if existing_user.username == username else "email"
            raise HTTPException(status_code=400, detail=f"A user with this {conflict} already exists")
        password = data.initial_password
        try:
            await user_manager.validate_password(data.initial_password, User(
                email=email,
                username=username,
                first_name=data.first_name,
                last_name=data.last_name,
            ))
        except fu_exceptions.InvalidPasswordException as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD", "reason": exc.reason}) from exc
        user_payload = {
            "username": username,
            "email": email,
            "password": password,
            "first_name": data.first_name,
            "last_name": data.last_name,
            "is_active": True,
            "must_change_password": True,
            "created_by": current_user.id,
        }
        try:
            # Keep account and employee creation in one transaction.
            created_user = User(
                **{key: value for key, value in user_payload.items() if key != "password"},
                hashed_password=user_manager.password_helper.hash(password),
            )
            session.add(created_user)
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail="A user with this email or username already exists") from exc
        user_id = created_user.id
        created_user.is_verified = True

        employee_data = EmployeeCreate(**data.model_dump(exclude={"create_user_account", "username", "initial_password"}, exclude_unset=True))
        employee_data.user_id = user_id
        employee = await EmployeeService(session).create_employee(employee_data, commit=False)
        await session.commit()

        return employee
    except Exception:
        await session.rollback()
        raise


@router.get("/{emp_id}", response_model=EmployeeDirectoryRead)
async def get_employee(
    emp_id: int,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    emp = await service.get_employee(emp_id)
    await require_employee_access(current_user, emp, "employee.view", session, allow_self=True)
    return service.enrich_directory(emp)


@router.get("/{emp_id}/work-history", response_model=PaginatedResponse[EmployeeWorkHistoryRead])
async def get_employee_work_history(
    emp_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[EmployeeWorkHistoryRead]:
    service = EmployeeService(session)
    employee = await service.get_employee(emp_id)
    await require_employee_access(current_user, employee, "employee.view", session, allow_self=True)
    return await service.work_history_page(
        emp_id,
        page,
        page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
