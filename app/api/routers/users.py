"""Authenticated account profile endpoints.

Employee provisioning and workforce lifecycle management belong to ERP-backed
``/employees`` routes. This router exposes the authenticated profile plus a
narrow Super Admin support surface for login security incidents; it does not
edit employee records, business roles, reporting lines, or other ERP-owned data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import record_audit_event
from core.auth import current_sensitive_user, fastapi_users, get_user_permissions
from core.auth_throttle import AuthThrottle, get_auth_throttle
from core.business_roles import resolve_business_access
from core.database import get_async_session
from core.request_context import client_ip
from core.sorting import TechnicalAccountSort
from db.models import Employee, User
from routers.auth_sessions import guard_throttle, record_throttle_failure
from schemas import UserPermissionsResponse, UserRead
from schemas.users import (
    PaginatedTechnicalAccountsResponse,
    SuperAdminAccountActionResponse,
    SuperAdminAccountStatusRequest,
    SuperAdminStepUpRequest,
    TemporaryPasswordResponse,
)
from services.user_admin_service import UserAdminService

router = APIRouter(prefix="/users", tags=["account"])


def _audit_context(request: Request) -> dict[str, str | None]:
    return {
        "ip_address": request.client.host if request.client else None,
        "request_id": getattr(request.state, "request_id", None),
    }


def _step_up_context(request: Request) -> dict:
    return {
        **_audit_context(request),
        "session_mfa_verified_at": getattr(getattr(request.state, "auth_session", None), "mfa_verified_at", None),
    }


async def _run_admin_action(
    request: Request,
    actor: User,
    session: AsyncSession,
    throttle: AuthThrottle,
    action,
):
    account = AuthThrottle.account_key(f"user:{actor.id}")
    await guard_throttle(throttle, request=request, account=account, scope="step_up")
    try:
        result = await action()
    except HTTPException as exc:
        if exc.status_code == 400 and exc.detail == "Current password is incorrect":
            await record_throttle_failure(throttle, request=request, account=account, scope="step_up")
            await record_audit_event(
                session,
                actor=actor,
                action="SUPER_ADMIN_STEP_UP_FAILED",
                entity_type="account_support",
                filters={"path": request.url.path, "reason": "invalid_password"},
                request_id=getattr(request.state, "request_id", None),
                ip_address=request.client.host if request.client else None,
            )
        raise
    await throttle.record_success(ip=client_ip(request), account=account, scope="step_up")
    return result


@router.get("/me", response_model=UserRead, summary="Get the authenticated account")
async def get_current_user_me(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UserRead:
    target_user = await session.scalar(select(User).where(User.id == user.id)) or user
    user_read = UserRead.model_validate(target_user)
    user_read.permissions = await get_user_permissions(target_user, session)
    employee = await session.scalar(select(Employee).where(Employee.user_id == target_user.id).limit(1))
    if employee:
        user_read.employee_id = employee.id
        user_read.employee_code = employee.employee_code
        user_read.role = employee.role
        # Resolved (not raw) role/scope, so rows written before the scope
        # columns existed report the access they actually have.
        access = resolve_business_access(employee)
        user_read.business_role = access.business_role
        user_read.scope_type = access.scope_type
    elif target_user.is_superuser:
        user_read.role = "SUPER_ADMIN"
    return user_read


@router.get("/me/permissions", response_model=UserPermissionsResponse, summary="Get account permissions")
async def get_current_user_permissions(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UserPermissionsResponse:
    return UserPermissionsResponse(permissions=await get_user_permissions(user, session))


@router.get(
    "/admin/accounts",
    response_model=PaginatedTechnicalAccountsResponse,
    summary="List workforce login accounts for technical support",
)
async def list_admin_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    sort_by: TechnicalAccountSort | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    actor: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedTechnicalAccountsResponse:
    return await UserAdminService(session).list_accounts(
        actor,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post(
    "/admin/accounts/{user_id}/temporary-password",
    response_model=TemporaryPasswordResponse,
    summary="Generate a temporary workforce-account password",
)
async def reset_admin_account_password(
    user_id: int,
    payload: SuperAdminStepUpRequest,
    request: Request,
    actor: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
) -> TemporaryPasswordResponse:
    password, revoked = await _run_admin_action(
        request,
        actor,
        session,
        throttle,
        lambda: UserAdminService(session).reset_password(
            actor, user_id, payload.current_password, **_step_up_context(request)
        ),
    )
    return TemporaryPasswordResponse(
        temporary_password=password,
        revoked_sessions=revoked,
        message="Temporary password generated. It is shown once and must be changed after sign-in.",
    )


@router.post(
    "/admin/accounts/{user_id}/revoke-sessions",
    response_model=SuperAdminAccountActionResponse,
    summary="Revoke all workforce-account sessions",
)
async def revoke_admin_account_sessions(
    user_id: int,
    payload: SuperAdminStepUpRequest,
    request: Request,
    actor: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
) -> SuperAdminAccountActionResponse:
    revoked = await _run_admin_action(
        request,
        actor,
        session,
        throttle,
        lambda: UserAdminService(session).revoke_sessions(
            actor, user_id, payload.current_password, **_step_up_context(request)
        ),
    )
    return SuperAdminAccountActionResponse(message="All sessions were revoked.", revoked_sessions=revoked)


@router.patch(
    "/admin/accounts/{user_id}/status",
    response_model=SuperAdminAccountActionResponse,
    summary="Suspend or reactivate a workforce login account",
)
async def update_admin_account_status(
    user_id: int,
    payload: SuperAdminAccountStatusRequest,
    request: Request,
    actor: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
) -> SuperAdminAccountActionResponse:
    revoked = await _run_admin_action(
        request,
        actor,
        session,
        throttle,
        lambda: UserAdminService(session).set_active(
            actor, user_id, payload.current_password, payload.is_active, **_step_up_context(request)
        ),
    )
    message = "Account reactivated." if payload.is_active else "Account suspended and sessions revoked."
    return SuperAdminAccountActionResponse(message=message, revoked_sessions=revoked)


@router.post(
    "/admin/accounts/{user_id}/mfa-reset",
    response_model=SuperAdminAccountActionResponse,
    summary="Reset a workforce account's authenticator",
)
async def reset_admin_account_mfa(
    user_id: int,
    payload: SuperAdminStepUpRequest,
    request: Request,
    actor: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
) -> SuperAdminAccountActionResponse:
    revoked = await _run_admin_action(
        request,
        actor,
        session,
        throttle,
        lambda: UserAdminService(session).reset_mfa(
            actor, user_id, payload.current_password, **_step_up_context(request)
        ),
    )
    return SuperAdminAccountActionResponse(
        message="Authenticator reset. The user must enroll again if policy requires it.",
        revoked_sessions=revoked,
    )
