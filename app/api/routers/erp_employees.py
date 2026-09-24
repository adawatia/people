from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import UserManager, get_user_manager, verify_erp_api_key
from core.database import get_async_session
from core.mobile import normalize_indian_mobile
from db.models import Employee, User
from schemas.employees import (
    EmployeeCreate,
    EmployeeDeactivateRequest,
    EmployeeOnboardingCreate,
    EmployeeRead,
    EmployeeUpdate,
)
from services.employee_service import EmployeeService

router = APIRouter(prefix="/integrations/erp/employees", tags=["erp-employees"])


@router.patch("/{employee_id}", response_model=EmployeeRead, summary="ERP update employee and linked profile", dependencies=[Depends(verify_erp_api_key)])
async def update_employee_from_erp(employee_id: int, data: EmployeeUpdate, session: AsyncSession = Depends(get_async_session)):
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    linked_user_id = employee.user_id
    result = await EmployeeService(session).update_employee(employee_id, data)
    user = await session.get(User, linked_user_id) if linked_user_id else None
    if user:
        updates = data.model_dump(exclude_unset=True)
        for field in ("first_name", "last_name"):
            if field in updates:
                setattr(user, field, updates[field])
        if updates.get("phone_number"):
            user.mobile_number = normalize_indian_mobile(updates["phone_number"])
        await session.commit()
    return result


@router.patch("/{employee_id}/deactivate", response_model=EmployeeRead, summary="ERP deactivate employee", dependencies=[Depends(verify_erp_api_key)])
async def deactivate_employee_from_erp(employee_id: int, payload: EmployeeDeactivateRequest | None = None, session: AsyncSession = Depends(get_async_session)):
    return await EmployeeService(session).deactivate_employee(employee_id, exit_date=payload.exit_date if payload else None, exit_reason=payload.exit_reason if payload else None)


@router.patch("/{employee_id}/activate", response_model=EmployeeRead, summary="ERP activate employee", dependencies=[Depends(verify_erp_api_key)])
async def activate_employee_from_erp(employee_id: int, session: AsyncSession = Depends(get_async_session)):
    return await EmployeeService(session).activate_employee(employee_id)


@router.post("", response_model=EmployeeRead, summary="ERP create employee and linked login", description="Creates one employee and one linked login account atomically. Requires an Indian mobile number and a strong temporary password.", dependencies=[Depends(verify_erp_api_key)])
async def create_employee_from_erp(
    data: EmployeeOnboardingCreate,
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    """Provision the employee and linked login from the ERP source of truth."""
    if not data.phone_number or not data.initial_password:
        raise HTTPException(status_code=400, detail="ERP must provide phone_number and initial_password")
    email = data.official_email or f"{data.username or data.employee_code}@invalid.local"
    username = (data.username or data.employee_code).strip().lower().replace(" ", ".")
    existing = await session.scalar(select(User).where((User.username == username) | (User.email == email)))
    if existing:
        raise HTTPException(status_code=409, detail="ERP employee login already exists")
    await user_manager.validate_password(data.initial_password, User(email=email, username=username, first_name=data.first_name, last_name=data.last_name))
    try:
        mobile_number = normalize_indian_mobile(data.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = User(username=username, email=email, first_name=data.first_name, last_name=data.last_name, mobile_number=mobile_number, is_active=True, is_verified=True, must_change_password=True, hashed_password=user_manager.password_helper.hash(data.initial_password))
    try:
        session.add(user)
        await session.flush()
        employee_data = data.model_copy(update={"user_id": user.id})
        employee_data = employee_data.model_dump(exclude={"create_user_account", "username", "initial_password"}, exclude_unset=True)
        employee = await EmployeeService(session).create_employee(EmployeeCreate(**employee_data), commit=False)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="An employee or login with the same code, mobile number, email, or username already exists") from exc
    return employee
