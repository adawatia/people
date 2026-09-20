import secrets
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import UserManager, fastapi_users, get_user_manager, require_permission
from core.email import get_email_service
from core.invitation import create_invitation_for_user
from core.settings import get_settings
from fastapi_users import exceptions as fu_exceptions
from core.database import get_async_session
from db.models import Role, User, UserRoleAssignment
from schemas.employees import (
    EmployeeCreate,
    EmployeeOnboardingCreate,
    EmployeeDeactivateRequest,
    EmployeeRead,
    EmployeeUpdate,
    EmployeeWorkHistoryRead,
    PaginatedEmployeesResponse,
)
from services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/", response_model=PaginatedEmployeesResponse)
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = None,
    unit_id: int | None = None,
    department_id: int | None = None,
    designation_id: int | None = None,
    status: str | None = None,
    reporting_manager_id: int | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedEmployeesResponse:
    service = EmployeeService(session)
    return await service.list_employees(
        page=page,
        page_size=page_size,
        q=q,
        unit_id=unit_id,
        department_id=department_id,
        designation_id=designation_id,
        status_filter=status,
        reporting_manager_id=reporting_manager_id,
    )


@router.post("/", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    data: EmployeeCreate,
    _: User = Depends(require_permission("employee.create")),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    return await service.create_employee(data)


@router.post("/onboard", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def onboard_employee(
    data: EmployeeOnboardingCreate,
    _: User = Depends(require_permission("employee.create")),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    """Create the HR record and, when requested, its linked portal account."""
    current_user = _
    user_id = data.user_id
    created_user = None
    raw_invite_token = None
    try:
        if data.create_user_account:
            email = data.official_email
            if not email:
                raise HTTPException(status_code=400, detail="Official email is required for a user account")
            if not data.send_invitation and not data.initial_password:
                raise HTTPException(status_code=400, detail="Provide an initial password when invitation email is disabled")
            username = data.username or email.split("@", 1)[0]
            username = username.lower().replace(" ", ".")
            existing_user = await session.scalar(
                select(User).where((User.username == username) | (User.email == email))
            )
            if existing_user:
                conflict = "username" if existing_user.username == username else "email"
                raise HTTPException(status_code=400, detail=f"A user with this {conflict} already exists")
            password = f"{secrets.token_urlsafe(24)}!Aa9"
            if data.initial_password:
                try:
                    await user_manager.validate_password(data.initial_password, User(
                        email=email,
                        username=username,
                        first_name=data.first_name,
                        last_name=data.last_name,
                    ))
                except fu_exceptions.InvalidPasswordException as exc:
                    raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD", "reason": exc.reason}) from exc
                password = data.initial_password
            user_payload = {
                "username": username,
                "email": email,
                "password": password,
                "first_name": data.first_name,
                "last_name": data.last_name,
                "is_active": True,
                "must_change_password": False,
                "created_by": current_user.id,
            }
            try:
                # Do not use UserManager.create here: FastAPI Users commits
                # immediately, which could leave an orphan account if the
                # subsequent employee insert fails.
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
            if data.initial_password:
                created_user.must_change_password = True
                created_user.is_verified = True
            employee_role = await session.scalar(select(Role).where(Role.role_name == "EMPLOYEE"))
            if employee_role:
                session.add(UserRoleAssignment(
                    user_id=created_user.id,
                    role_id=employee_role.role_id,
                    scope_type="organization",
                    scope_id=None,
                    assigned_by=current_user.id,
                ))
            if data.send_invitation and not data.initial_password:
                raw_invite_token = create_invitation_for_user(created_user)
                created_user.is_verified = False

        employee_data = EmployeeCreate(**data.model_dump(exclude={"create_user_account", "username", "send_invitation", "initial_password"}, exclude_unset=True))
        employee_data.user_id = user_id
        employee = await EmployeeService(session).create_employee(employee_data, commit=False)
        await session.commit()

        if created_user and raw_invite_token:
            settings = get_settings()
            frontend_url = (settings.frontend_url or "http://localhost:3000").rstrip("/")
            invite_url = f"{frontend_url}/auth/invitation?token={raw_invite_token}"
            asyncio.create_task(get_email_service().send_user_invitation_email(
                to_email=created_user.email,
                user_name=created_user.first_name or created_user.username,
                username=created_user.username,
                role_name="Employee",
                invite_url=invite_url,
            ))
        return employee
    except Exception:
        await session.rollback()
        raise


@router.get("/{emp_id}", response_model=EmployeeRead)
async def get_employee(
    emp_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    emp = await service.get_employee(emp_id)
    return service.enrich(emp)


@router.patch("/{emp_id}", response_model=EmployeeRead)
async def update_employee(
    emp_id: int,
    data: EmployeeUpdate,
    _: User = Depends(require_permission("employee.update")),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    return await service.update_employee(emp_id, data)


@router.patch("/{emp_id}/deactivate", response_model=EmployeeRead)
async def deactivate_employee(
    emp_id: int,
    payload: EmployeeDeactivateRequest | None = None,
    _: User = Depends(require_permission("employee.deactivate")),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    exit_date = payload.exit_date if payload else None
    exit_reason = payload.exit_reason if payload else None
    return await service.deactivate_employee(emp_id, exit_date=exit_date, exit_reason=exit_reason)


@router.patch("/{emp_id}/activate", response_model=EmployeeRead)
async def activate_employee(
    emp_id: int,
    _: User = Depends(require_permission("employee.update")),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    return await service.activate_employee(emp_id)


@router.delete("/{emp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    emp_id: int,
    _: User = Depends(require_permission("employee.delete")),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    service = EmployeeService(session)
    await service.delete_employee(emp_id)


@router.get("/{emp_id}/work-history", response_model=list[EmployeeWorkHistoryRead])
async def get_employee_work_history(
    emp_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[EmployeeWorkHistoryRead]:
    service = EmployeeService(session)
    return await service.get_work_history(emp_id)
