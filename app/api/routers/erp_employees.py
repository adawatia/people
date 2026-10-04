from fastapi import APIRouter, Depends, HTTPException
from fastapi_users.exceptions import InvalidPasswordException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import UserManager, get_user_manager
from core.database import get_async_session
from core.erp_auth import require_erp_scope
from core.erp_sync import acquire_erp_upsert_lock
from core.mobile import normalize_indian_mobile
from db.models import Employee, User
from schemas.employees import (
    EmployeeCreate,
    EmployeeDeactivateRequest,
    EmployeeOnboardingCreate,
    EmployeeRead,
    EmployeeUpdate,
    EmployeeUpsert,
)
from services.employee_service import EmployeeService

router = APIRouter(prefix="/integrations/erp/employees", tags=["erp-employees"])


@router.put(
    "/by-erp-id/{erp_id}",
    response_model=EmployeeRead,
    summary="Idempotently upsert an ERP employee",
    description=(
        "Creates the linked login only on the first request. Later requests update ERP-owned employee fields "
        "without changing the account password."
    ),
    dependencies=[Depends(require_erp_scope("employees:write"))],
)
async def upsert_employee_from_erp(
    erp_id: str,
    data: EmployeeUpsert,
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    if data.erp_id is not None and data.erp_id != erp_id:
        raise HTTPException(status_code=422, detail="erp_id in the body must match the URL")
    await acquire_erp_upsert_lock(session, "employee", erp_id)
    existing = await session.scalar(select(Employee).where(Employee.erp_id == erp_id))
    if existing is None:
        fields = data.model_dump(exclude_unset=True)
        fields["erp_id"] = erp_id
        if fields.get("status", "ACTIVE") != "ACTIVE":
            raise HTTPException(status_code=422, detail="New employees must be ACTIVE; deactivate after creation")
        try:
            onboarding = EmployeeOnboardingCreate.model_validate(fields)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        return await _create_employee_from_erp(onboarding, user_manager, session)

    if "employee_code" in data.model_fields_set and not data.employee_code:
        raise HTTPException(status_code=422, detail="employee_code cannot be empty")
    if data.employee_code is not None and data.employee_code != existing.employee_code:
        raise HTTPException(status_code=409, detail="employee_code cannot change for an existing ERP employee")
    if "first_name" in data.model_fields_set and not data.first_name:
        raise HTTPException(status_code=422, detail="first_name cannot be empty")
    for field in ("role", "employment_type", "overtime_eligible"):
        if field in data.model_fields_set and getattr(data, field) is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
    employee_id = existing.id
    linked_user_id = existing.user_id

    update_fields = data.model_dump(
        exclude={
            "erp_id",
            "employee_code",
            "user_id",
            "create_user_account",
            "username",
            "initial_password",
        },
        exclude_unset=True,
    )
    previous_status = existing.status
    requested_status = update_fields.pop("status", None)
    effective_status = requested_status or previous_status
    if {"exit_date", "exit_reason"} & data.model_fields_set and effective_status != "INACTIVE":
        raise HTTPException(status_code=422, detail="exit fields require INACTIVE status")
    exit_date = update_fields.pop("exit_date", None) if requested_status != previous_status else None
    exit_reason = update_fields.pop("exit_reason", None) if requested_status != previous_status else None
    if "status" in data.model_fields_set and requested_status not in {"ACTIVE", "INACTIVE"}:
        raise HTTPException(status_code=422, detail="status must be ACTIVE or INACTIVE")
    if requested_status == "ACTIVE" and previous_status == "ACTIVE":
        update_fields.pop("exit_date", None)
        update_fields.pop("exit_reason", None)
    mobile_number = None
    if "phone_number" in data.model_fields_set and not data.phone_number:
        raise HTTPException(status_code=422, detail="phone_number cannot be empty for a linked login")
    if update_fields.get("phone_number"):
        try:
            mobile_number = normalize_indian_mobile(update_fields["phone_number"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    service = EmployeeService(session)
    try:
        if update_fields:
            await service.update_employee(employee_id, EmployeeUpdate(**update_fields), commit=False)
        linked_user = await session.get(User, linked_user_id) if linked_user_id else None
        if linked_user:
            for field in ("first_name", "last_name"):
                if field in update_fields:
                    setattr(linked_user, field, update_fields[field])
            if mobile_number:
                linked_user.mobile_number = mobile_number
        if requested_status is not None and requested_status != previous_status:
            if requested_status == "INACTIVE":
                await service.deactivate_employee(
                    employee_id, exit_date=exit_date, exit_reason=exit_reason, commit=False
                )
            elif requested_status == "ACTIVE":
                await service.activate_employee(employee_id, commit=False)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Employee or linked login conflicts with existing data") from exc
    session.expire_all()
    return service.enrich(await service.get_employee(employee_id))


@router.patch(
    "/{employee_id}/deactivate",
    response_model=EmployeeRead,
    summary="ERP deactivate employee",
    dependencies=[Depends(require_erp_scope("employees:write"))],
)
async def deactivate_employee_from_erp(
    employee_id: int,
    payload: EmployeeDeactivateRequest | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    return await EmployeeService(session).deactivate_employee(
        employee_id,
        exit_date=payload.exit_date if payload else None,
        exit_reason=payload.exit_reason if payload else None,
    )


@router.patch(
    "/{employee_id}/activate",
    response_model=EmployeeRead,
    summary="ERP activate employee",
    dependencies=[Depends(require_erp_scope("employees:write"))],
)
async def activate_employee_from_erp(employee_id: int, session: AsyncSession = Depends(get_async_session)):
    return await EmployeeService(session).activate_employee(employee_id)


async def _create_employee_from_erp(
    data: EmployeeOnboardingCreate,
    user_manager: UserManager,
    session: AsyncSession,
) -> EmployeeRead:
    """Provision the employee and linked login from the ERP source of truth."""
    if not data.phone_number or not data.initial_password:
        raise HTTPException(status_code=422, detail="ERP must provide phone_number and initial_password")
    email = data.official_email or f"{data.username or data.employee_code}@invalid.local"
    username = (data.username or data.employee_code).strip().lower().replace(" ", ".")
    existing = await session.scalar(select(User).where((User.username == username) | (User.email == email)))
    if existing:
        raise HTTPException(status_code=409, detail="ERP employee login already exists")
    try:
        await user_manager.validate_password(
            data.initial_password,
            User(email=email, username=username, first_name=data.first_name, last_name=data.last_name),
        )
    except InvalidPasswordException as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_PASSWORD", "reason": exc.reason},
        ) from exc
    try:
        mobile_number = normalize_indian_mobile(data.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = User(
        username=username,
        email=email,
        first_name=data.first_name,
        last_name=data.last_name,
        mobile_number=mobile_number,
        is_active=True,
        is_verified=True,
        must_change_password=True,
        hashed_password=user_manager.password_helper.hash(data.initial_password),
    )
    try:
        session.add(user)
        await session.flush()
        employee_data = data.model_copy(update={"user_id": user.id})
        employee_data = employee_data.model_dump(
            exclude={"create_user_account", "username", "initial_password"}, exclude_unset=True
        )
        employee = await EmployeeService(session).create_employee(EmployeeCreate(**employee_data), commit=False)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="An employee or login with the same code, mobile number, email, or username already exists",
        ) from exc
    return employee
