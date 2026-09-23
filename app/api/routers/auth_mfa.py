"""Multi-factor authentication for privileged accounts.

Flow split, so a stolen password alone can never reset an existing second factor:

* **Challenge endpoints** (unauthenticated, reachable only with a short-lived
  challenge token issued *after* a correct password):
  ``POST /auth/mfa/enroll``  — first-time enrolment (only when the account has no
  factor yet), ``POST /auth/mfa/activate`` — confirm the factor and sign in,
  ``POST /auth/mfa/verify``  — normal second-factor verification (TOTP or a
  single-use recovery code).
* **Management endpoints** (authenticated + password re-verified):
  ``POST /auth/mfa/reset`` — issue a new secret, ``POST /auth/mfa/disable`` —
  remove MFA, ``GET /auth/mfa/status`` — report enrolment state.

The challenge token is signed with the same key as an access token but a
different audience, so it cannot be replayed as one.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import UserManager, fastapi_users, get_user_manager
from core.auth_throttle import AuthThrottle, get_auth_throttle
from core.database import get_async_session
from core.request_context import client_ip, request_id
from db.models import User
from routers.auth_sessions import guard_throttle, record_throttle_failure
from schemas.auth import (
    LoginResponse,
    MessageResponse,
    MfaChallengeRequest,
    MfaConfirmRequest,
    MfaEnrollmentResponse,
    MfaEnrollRequest,
    MfaPasswordRequest,
    MfaStatusResponse,
)
from services.auth_service import AuthService

router = APIRouter(prefix="/auth/mfa", tags=["auth-account"])


def _session_payload(issued, *, must_change_password: bool) -> LoginResponse:
    return LoginResponse(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.access_expires_in,
        session_id=issued.session_id,
        refresh_expires_at=issued.refresh_expires_at,
        absolute_expires_at=issued.absolute_expires_at,
        must_change_password=must_change_password,
    )


@router.post(
    "/enroll",
    response_model=MfaEnrollmentResponse,
    summary="Start first-time MFA enrolment",
    description=(
        "Returns a TOTP secret, its otpauth:// provisioning URI and single-use "
        "recovery codes. Only available while the account has no second factor, so "
        "possession of a password cannot replace an enrolled device."
    ),
)
async def enroll_mfa(
    payload: MfaEnrollRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
):
    service = AuthService(session)
    user_id, enrollment_required = service.resolve_mfa_challenge(payload.mfa_token)
    account = AuthThrottle.account_key(f"user:{user_id}")
    await guard_throttle(throttle, request=request, account=account, scope="mfa")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in again to continue")
    if not enrollment_required or user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account already has an authenticator. Sign in with it, or reset it from account settings.",
        )
    enrollment = await service.start_enrollment(user)
    return MfaEnrollmentResponse(
        secret=enrollment.secret,
        otpauth_uri=enrollment.otpauth_uri,
        recovery_codes=enrollment.recovery_codes,
    )


@router.post(
    "/activate",
    response_model=LoginResponse,
    summary="Confirm MFA enrolment and sign in",
)
async def activate_mfa(
    payload: MfaChallengeRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
):
    service = AuthService(session)
    user_id, enrollment_required = service.resolve_mfa_challenge(payload.mfa_token)
    account = AuthThrottle.account_key(f"user:{user_id}")
    await guard_throttle(throttle, request=request, account=account, scope="mfa")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in again to continue")
    if not enrollment_required:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account is already enrolled")

    try:
        await service.activate_enrollment(
            user,
            payload.code,
            ip_address=client_ip(request),
            request_id=request_id(request),
        )
    except HTTPException:
        await record_throttle_failure(throttle, request=request, account=account, scope="mfa")
        raise

    await throttle.record_success(ip=client_ip(request), account=account, scope="mfa")
    issued = await service.issue_session(
        user,
        ip_address=client_ip(request),
        request_id=request_id(request),
        mfa_verified=True,
    )
    return _session_payload(issued, must_change_password=user.must_change_password)


@router.post(
    "/verify",
    response_model=LoginResponse,
    summary="Verify second factor and sign in",
    description="Accepts a 6-digit TOTP code or a single-use recovery code.",
)
async def verify_mfa(
    payload: MfaChallengeRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
):
    service = AuthService(session)
    user_id, _enrollment_required = service.resolve_mfa_challenge(payload.mfa_token)
    account = AuthThrottle.account_key(f"user:{user_id}")
    await guard_throttle(throttle, request=request, account=account, scope="mfa")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in again to continue")
    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account has no authenticator yet. Start enrolment to finish signing in.",
        )

    verified = await service.verify_mfa(
        user,
        payload.code,
        ip_address=client_ip(request),
        request_id=request_id(request),
    )
    if not verified:
        await record_throttle_failure(throttle, request=request, account=account, scope="mfa")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That code is not valid")

    await throttle.record_success(ip=client_ip(request), account=account, scope="mfa")
    issued = await service.issue_session(
        user,
        ip_address=client_ip(request),
        request_id=request_id(request),
        mfa_verified=True,
    )
    return _session_payload(issued, must_change_password=user.must_change_password)


def _status_payload(user: User) -> MfaStatusResponse:
    hashes = json.loads(user.mfa_recovery_code_hashes) if user.mfa_recovery_code_hashes else []
    return MfaStatusResponse(
        enabled=bool(user.mfa_enabled),
        enrolled_at=user.mfa_enrolled_at,
        last_verified_at=user.last_mfa_verified_at,
        recovery_codes_remaining=len(hashes) if isinstance(hashes, list) else 0,
    )


@router.get("/status", response_model=MfaStatusResponse, summary="My MFA status")
async def mfa_status(
    user: User = Depends(fastapi_users.current_user(active=True)),
):
    return _status_payload(user)


@router.post(
    "/confirm",
    response_model=MfaStatusResponse,
    summary="Confirm a new authenticator from my session",
    description=(
        "Opt in to MFA from account settings: the password is re-verified, then the "
        "code must match the pending secret before the factor is enabled. Mirrors "
        "the login-time activation so both paths share one rule."
    ),
)
async def confirm_mfa(
    payload: MfaConfirmRequest,
    request: Request,
    user: User = Depends(fastapi_users.current_user(active=True)),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """Step-up protected: password *and* a code from the pending secret."""
    verified, _ = manager.password_helper.verify_and_update(payload.current_password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    await AuthService(session).activate_enrollment(
        user,
        payload.code,
        ip_address=client_ip(request),
        request_id=request_id(request),
    )
    return _status_payload(user)


@router.post("/reset", response_model=MfaEnrollmentResponse, summary="Re-issue my authenticator secret")
async def reset_mfa(
    payload: MfaPasswordRequest,
    request: Request,
    user: User = Depends(fastapi_users.current_user(active=True)),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """Step-up protected: the current password must be supplied again."""
    verified, _ = manager.password_helper.verify_and_update(payload.current_password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    enrollment = await AuthService(session).start_enrollment(user)
    return MfaEnrollmentResponse(
        secret=enrollment.secret,
        otpauth_uri=enrollment.otpauth_uri,
        recovery_codes=enrollment.recovery_codes,
    )


@router.post("/disable", response_model=MessageResponse, summary="Remove my authenticator")
async def disable_mfa(
    payload: MfaPasswordRequest,
    request: Request,
    user: User = Depends(fastapi_users.current_user(active=True)),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """Step-up protected: the password is re-verified before the factor is removed.

    Removal is rejected while policy requires MFA for this account, so a stolen
    password cannot be used to strip the second factor and then sign in with it.
    """
    verified, _ = manager.password_helper.verify_and_update(payload.current_password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    service = AuthService(session)
    if service.policy_requires_mfa(user) and user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account requires MFA. An administrator must change the policy first.",
        )
    await service.disable_mfa(user, ip_address=client_ip(request), request_id=request_id(request))
    return MessageResponse(message="Authenticator removed")
