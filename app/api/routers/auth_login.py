from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from core.auth import UserManager, fastapi_users, get_jwt_strategy, get_user_manager, require_permission
from core.database import get_async_session
from core.employee_access import require_employee_access
from db.models import AuthSession, Employee, User, now_ist
from core.mobile import normalize_indian_mobile
from core.auth import verify_erp_api_key

router = APIRouter(prefix="/auth")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=12)
    model_config = {"json_schema_extra": {"example": {"current_password": "CurrentPassword@123", "new_password": "NewStrongPassword@456"}}}


class TemporaryPasswordRequest(BaseModel):
    temporary_password: str = Field(min_length=12)
    model_config = {"json_schema_extra": {"example": {"temporary_password": "TemporaryPassword@123"}}}


class UsernameChangeRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    model_config = {"json_schema_extra": {"example": {"username": "platform.admin"}}}


async def _reset_password(employee: Employee, payload: TemporaryPasswordRequest, manager: UserManager, session: AsyncSession):
    if employee.user_id is None:
        raise HTTPException(status_code=404, detail="Employee has no login account")
    user = await session.get(User, employee.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Login account not found")
    await manager.validate_password(payload.temporary_password, user)
    user.hashed_password = manager.password_helper.hash(payload.temporary_password)
    user.must_change_password = True
    await session.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=now_ist()))
    await session.commit()
    return {"message": "Temporary password set. The employee must change it after login."}


async def _login(form: OAuth2PasswordRequestForm, manager: UserManager, session: AsyncSession, *, super_admin: bool):
    identity = form.username.strip()
    if not super_admin:
        try:
            identity = normalize_indian_mobile(identity) or identity
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif identity.startswith("+") or identity.isdigit() or "@" in identity:
        raise HTTPException(status_code=400, detail="This sign-in uses a username")

    user = await manager.authenticate(type("Credentials", (), {"username": identity, "password": form.password})())
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login credentials")
    if super_admin and not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super Admin access required")
    if not super_admin:
        employee = await session.scalar(select(Employee).where(Employee.user_id == user.id))
        if employee is None:
            raise HTTPException(status_code=403, detail="This account is not linked to an employee")

    token = await get_jwt_strategy().write_token(user)
    return {"access_token": token, "token_type": "bearer", "must_change_password": user.must_change_password}


@router.post("/employee/login", tags=["auth-employee"], summary="Employee login", description="OAuth2 form fields: username is the employee's Indian 10-digit mobile number; password is the current password.")
async def employee_login(
    form: OAuth2PasswordRequestForm = Depends(),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    return await _login(form, manager, session, super_admin=False)


@router.post("/super-admin/login", tags=["auth-super-admin"], summary="Super Admin login", description="OAuth2 form fields: username is the technical account username only; email and mobile numbers are not accepted.")
async def super_admin_login(
    form: OAuth2PasswordRequestForm = Depends(),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    return await _login(form, manager, session, super_admin=True)


@router.post("/change-password", tags=["auth-account"], summary="Change own password")
async def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(fastapi_users.current_user(active=True)),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    verified, _ = manager.password_helper.verify_and_update(payload.current_password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        await manager.validate_password(payload.new_password, user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user.hashed_password = manager.password_helper.hash(payload.new_password)
    user.must_change_password = False
    await session.commit()
    return {"message": "Password changed successfully"}


@router.patch("/super-admin/username", tags=["auth-super-admin"], summary="Change Super Admin username")
async def change_super_admin_username(
    payload: UsernameChangeRequest,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
):
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Technical administrator access required")
    username = payload.username.strip()
    existing = await session.scalar(select(User).where(User.username == username, User.id != user.id))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already in use")
    user.username = username
    await session.commit()
    return {"message": "Username updated successfully", "username": username}


@router.post("/hr/employees/{employee_id}/password-reset", tags=["auth-hr"], summary="Set employee temporary password")
async def hr_password_reset(
    employee_id: int,
    payload: TemporaryPasswordRequest,
    manager: UserManager = Depends(get_user_manager),
    _: User = Depends(require_permission("user.update")),
    session: AsyncSession = Depends(get_async_session),
):
    """HR user administration: permission + row scope, not a role check."""
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(_, employee, "user.update", session)
    return await _reset_password(employee, payload, manager, session)


@router.post("/integrations/erp/employees/{employee_id}/password-reset", tags=["erp-employees"], summary="ERP set employee temporary password", dependencies=[Depends(verify_erp_api_key)])
async def erp_password_reset(
    employee_id: int,
    payload: TemporaryPasswordRequest,
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await _reset_password(employee, payload, manager, session)
