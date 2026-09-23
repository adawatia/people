"""Human authentication: business login, Super Admin login, credential changes.

Three authentication domains stay separate (see the architecture reference):
business users, the Super Admin technical identity, and ERP machine auth
(``/api/v1/integrations/erp/**``).  Business *roles* never choose a login
endpoint — an employee, manager, unit HR, organization HR and organization owner
all authenticate through ``/auth/employee/login`` and only then have their
permissions and scope resolved.

Both login endpoints now issue a session directly (access + rotating refresh)
instead of a long-lived intermediate bearer token, and both are throttled by
account, source IP and the pair.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import add_audit_event
from core.auth import UserManager, fastapi_users, get_user_manager, require_permission, verify_erp_api_key
from core.auth_throttle import AuthThrottle, get_auth_throttle
from core.database import get_async_session
from core.employee_access import require_employee_access
from core.mobile import normalize_indian_mobile
from core.request_context import client_ip, request_id, user_agent
from db.models import Employee, User
from routers.auth_sessions import guard_throttle, record_throttle_failure
from schemas.auth import LoginResponse
from services.auth_service import (
    INVALID_CREDENTIALS,
    AuditAction,
    AuthService,
    IssuedSession,
    MfaChallenge,
)

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
    # Changing the identifier of a break-glass account is a credential change, so
    # it is a step-up operation: the current password must be supplied again.
    current_password: str = Field(min_length=1)
    model_config = {"json_schema_extra": {"example": {"username": "platform.admin", "current_password": "CurrentPassword@123"}}}


def normalize_business_identity(identity: str) -> str:
    """Resolve a business login identifier.

    The login field accepts a mobile number, an email address or a username, so
    only values that actually look like a phone number are put through the
    strict Indian-mobile normaliser; everything else is passed to the user
    lookup untouched.  (Previously any non-mobile value was rejected, which
    silently made email/username sign-in unreachable despite being documented.)
    """
    candidate = (identity or "").strip()
    if not candidate or "@" in candidate:
        return candidate
    digits = re.sub(r"\D", "", candidate)
    if len(digits) >= 10:
        return normalize_indian_mobile(candidate) or candidate
    return candidate


def account_key(identity: str) -> str:
    """Throttle key for an account, normalised the same way on every path."""
    return AuthThrottle.account_key(normalize_business_identity(identity).lower())


def _session_payload(issued: IssuedSession, *, must_change_password: bool) -> LoginResponse:
    return LoginResponse(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.access_expires_in,
        session_id=issued.session_id,
        refresh_expires_at=issued.refresh_expires_at,
        absolute_expires_at=issued.absolute_expires_at,
        must_change_password=must_change_password,
    )


def _mfa_payload(challenge: MfaChallenge) -> LoginResponse:
    return LoginResponse(
        mfa_required=True,
        mfa_enrollment_required=challenge.enrollment_required,
        mfa_token=challenge.token,
        mfa_expires_in=challenge.expires_in,
    )


async def _authenticate_human(
    *,
    form: OAuth2PasswordRequestForm,
    manager: UserManager,
    session: AsyncSession,
    request: Request,
    throttle: AuthThrottle,
    super_admin: bool,
) -> tuple[User, Employee | None]:
    """Verify credentials for either human domain, throttled and audited."""
    policy_scope = "login"
    identity = (form.username or "").strip()
    key = account_key(identity or "anonymous")

    if not identity:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    if not super_admin:
        try:
            identity = normalize_business_identity(identity)
        except ValueError as exc:
            # A malformed *number* is a UX error, not an account-probing oracle,
            # but it is still counted so a script cannot ignore throttling.
            await record_throttle_failure(throttle, request=request, account=key, scope=policy_scope)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif identity.startswith("+") or identity.isdigit() or "@" in identity:
        await record_throttle_failure(throttle, request=request, account=key, scope=policy_scope)
        raise HTTPException(status_code=400, detail="This sign-in uses a username")

    user = await manager.authenticate(
        type("Credentials", (), {"username": identity, "password": form.password})()
    )
    if user is None or not user.is_active:
        await record_throttle_failure(throttle, request=request, account=key, scope=policy_scope)
        await AuthService(session).record_login(
            user=None,
            identity=identity,
            success=False,
            privileged=super_admin,
            reason="invalid_credentials",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=request_id(request),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    if super_admin and not user.is_superuser:
        # Same generic message: a valid employee credential must not learn that a
        # privileged endpoint exists, let alone that this account is not it.
        await record_throttle_failure(throttle, request=request, account=key, scope=policy_scope)
        await AuthService(session).record_login(
            user=user,
            identity=identity,
            success=False,
            privileged=True,
            reason="not_privileged",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=request_id(request),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    employee = None
    if not super_admin:
        employee = await session.scalar(select(Employee).where(Employee.user_id == user.id))
        if employee is None:
            # Reached only with a *correct* password, so this cannot enumerate
            # accounts for an attacker; it tells a real user to use the technical
            # sign-in instead of leaving them stuck.
            await AuthService(session).record_login(
                user=user,
                identity=identity,
                success=False,
                privileged=False,
                reason="no_employee_profile",
                ip_address=client_ip(request),
                user_agent=user_agent(request),
                request_id=request_id(request),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is a technical account. Use the technical sign-in.",
            )

    return user, employee


async def _login(
    form: OAuth2PasswordRequestForm,
    manager: UserManager,
    session: AsyncSession,
    request: Request,
    throttle: AuthThrottle,
    *,
    super_admin: bool,
) -> LoginResponse:
    account = account_key(form.username or "anonymous")
    await guard_throttle(throttle, request=request, account=account, scope="login")
    service = AuthService(session)
    user, _employee = await _authenticate_human(
        form=form,
        manager=manager,
        session=session,
        request=request,
        throttle=throttle,
        super_admin=super_admin,
    )

    await throttle.record_success(ip=client_ip(request), account=account, scope="login")

    if service.mfa_required(user):
        challenge = await service.begin_mfa_challenge(
            user,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=request_id(request),
        )
        await service.record_login(
            user=user,
            identity=form.username,
            success=True,
            privileged=super_admin,
            reason="mfa_challenge_issued",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=request_id(request),
        )
        return _mfa_payload(challenge)

    issued = await service.issue_session(
        user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=request_id(request),
    )
    await service.record_login(
        user=user,
        identity=form.username,
        success=True,
        privileged=super_admin,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=request_id(request),
    )
    return _session_payload(issued, must_change_password=user.must_change_password)


@router.post(
    "/employee/login",
    tags=["auth-employee"],
    response_model=LoginResponse,
    summary="Business login (all workforce roles)",
    description=(
        "OAuth2 form fields: ``username`` is the employee's Indian mobile number, "
        "email address or username; ``password`` is the current password. Every "
        "workforce user — employee, manager, unit HR, organization HR, "
        "organization owner — signs in here; permissions and scope are resolved "
        "afterwards via /users/me."
    ),
)
async def employee_login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
):
    return await _login(
        form, manager, session, request, throttle, super_admin=False
    )


@router.post(
    "/super-admin/login",
    tags=["auth-super-admin"],
    response_model=LoginResponse,
    summary="Super Admin login",
    description=(
        "Technical account sign-in. ``username`` only (email and mobile numbers are "
        "rejected). Returns an MFA challenge when MFA_REQUIRED_FOR_SUPER_ADMIN is "
        "enabled; session policy is stricter than for business users."
    ),
)
async def super_admin_login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
):
    return await _login(
        form, manager, session, request, throttle, super_admin=True
    )


@router.post("/change-password", tags=["auth-account"], summary="Change own password")
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    user: User = Depends(fastapi_users.current_user(active=True)),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """Rotate the password and end every session, including this one.

    Deliberate policy: a password change invalidates all outstanding refresh
    tokens, so a stolen session cannot survive the remediation.  The user signs in
    again with the new password — for privileged accounts that is also the
    required behaviour.
    """
    verified, _ = manager.password_helper.verify_and_update(payload.current_password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        await manager.validate_password(payload.new_password, user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user.hashed_password = manager.password_helper.hash(payload.new_password)
    user.must_change_password = False
    service = AuthService(session)
    await service.revoke_all(
        user,
        reason="password_changed",
        action=AuditAction.PASSWORD_CHANGED,
        ip_address=client_ip(request),
        request_id=request_id(request),
    )
    return {
        "message": "Password changed. All sessions were ended — sign in again with your new password.",
        "reauthentication_required": True,
    }


@router.patch("/super-admin/username", tags=["auth-super-admin"], summary="Change Super Admin username")
async def change_super_admin_username(
    payload: UsernameChangeRequest,
    request: Request,
    user: User = Depends(fastapi_users.current_user(active=True)),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """Step-up protected: the current password is re-verified before the change."""
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Technical administrator access required")
    verified, _ = manager.password_helper.verify_and_update(payload.current_password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    username = payload.username.strip()
    existing = await session.scalar(select(User).where(User.username == username, User.id != user.id))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already in use")

    user.username = username
    add_audit_event(
        session,
        actor=user,
        action="AUTH_USERNAME_CHANGED",
        entity_type="user",
        entity_id=str(user.id),
        filters={"username": username},
        ip_address=client_ip(request),
        request_id=request_id(request),
    )
    await session.commit()
    return {"message": "Username updated successfully", "username": username}


async def _reset_password(
    employee: Employee,
    payload: TemporaryPasswordRequest,
    manager: UserManager,
    session: AsyncSession,
    *,
    request: Request | None,
    source: str,
):
    if employee.user_id is None:
        raise HTTPException(status_code=404, detail="Employee has no login account")
    user = await session.get(User, employee.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Login account not found")
    await manager.validate_password(payload.temporary_password, user)
    user.hashed_password = manager.password_helper.hash(payload.temporary_password)
    user.must_change_password = True
    service = AuthService(session)
    await service.revoke_all(
        user,
        reason=f"password_reset:{source}",
        action=AuditAction.PASSWORD_RESET,
        ip_address=client_ip(request),
        request_id=request_id(request),
    )
    return {
        "message": "Temporary password set. Existing sessions were revoked and the employee must change it after login.",
        "sessions_revoked": True,
    }


@router.post("/hr/employees/{employee_id}/password-reset", tags=["auth-hr"], summary="Set employee temporary password")
async def hr_password_reset(
    employee_id: int,
    payload: TemporaryPasswordRequest,
    request: Request,
    manager: UserManager = Depends(get_user_manager),
    _: User = Depends(require_permission("user.update")),
    session: AsyncSession = Depends(get_async_session),
):
    """HR user administration: permission + row scope, not a role check."""
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(_, employee, "user.update", session)
    return await _reset_password(employee, payload, manager, session, request=request, source="hr")


@router.post(
    "/integrations/erp/employees/{employee_id}/password-reset",
    tags=["erp-employees"],
    summary="ERP set employee temporary password",
    dependencies=[Depends(verify_erp_api_key)],
)
async def erp_password_reset(
    employee_id: int,
    payload: TemporaryPasswordRequest,
    request: Request,
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await _reset_password(employee, payload, manager, session, request=request, source="erp")
