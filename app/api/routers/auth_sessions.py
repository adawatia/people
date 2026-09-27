"""Rotating refresh sessions and signed-in-device management.

Routes stay thin: they validate the request, enforce the authentication-specific
throttle, and delegate every lifecycle decision to ``services/auth_service.py``.

URLs are unchanged from the previous implementation (``POST /auth/session``,
``POST /auth/session/refresh``, ``DELETE /auth/session``) so existing clients —
notably the Nitro BFF — keep working; the session-management endpoints are new.
"""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import current_sensitive_user
from core.auth_throttle import AuthThrottle, get_auth_throttle
from core.database import get_async_session
from core.request_context import client_ip, request_id, user_agent
from core.settings import get_settings
from core.tokens import ACCESS_TOKEN_AUDIENCE, decode_token, token_fingerprint
from db.models import User
from schemas.auth import (
    MessageResponse,
    RefreshSessionRequest,
    SessionIssuedResponse,
    SessionSummaryResponse,
)
from services.auth_service import (
    SESSION_ENDED,
    AuthService,
    IssuedSession,
    SessionSummary,
)

router = APIRouter(prefix="/auth", tags=["auth-session"])
settings = get_settings()


def _issued(issued: IssuedSession) -> SessionIssuedResponse:
    return SessionIssuedResponse(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.access_expires_in,
        session_id=issued.session_id,
        refresh_expires_at=issued.refresh_expires_at,
        absolute_expires_at=issued.absolute_expires_at,
    )


def _summaries(items: list[SessionSummary]) -> list[SessionSummaryResponse]:
    return [SessionSummaryResponse(**vars(item)) for item in items]


def raise_throttled(retry_after_seconds: int) -> None:
    """Reject a throttled attempt with a machine-readable retry hint."""
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many attempts. Please wait and try again.",
        headers={"Retry-After": str(max(1, retry_after_seconds))},
    )


async def guard_throttle(
    throttle: AuthThrottle,
    *,
    request: Request,
    account: str | None,
    scope: str,
) -> None:
    """Reject before doing work when the caller is already blocked."""
    decision = await throttle.check(ip=client_ip(request), account=account, scope=scope)
    if not decision.allowed:
        raise_throttled(decision.retry_after_seconds)
    await throttle.apply_delay(decision)


async def record_throttle_failure(throttle: AuthThrottle, *, request: Request, account: str | None, scope: str) -> None:
    """Count a failure; escalate to a 429 once the budget is exhausted."""
    decision = await throttle.record_failure(ip=client_ip(request), account=account, scope=scope)
    if not decision.allowed:
        raise_throttled(decision.retry_after_seconds)


def current_session_id(request: Request | None) -> int | None:
    """Session id claimed by the presented access token (``sid``), if any.

    Used only for labelling the current device; it is never trusted for
    authorization.
    """
    if request is None:
        return None
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = decode_token(token, secret=settings.jwt_secret, audience=ACCESS_TOKEN_AUDIENCE)
    except jwt.PyJWTError:
        return None
    session_id = payload.get("sid")
    return int(session_id) if isinstance(session_id, int | str) and str(session_id).isdigit() else None


@router.post(
    "/session",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionIssuedResponse,
    summary="Create browser session",
    description=(
        "Creates an additional refresh session for the authenticated caller. "
        "Login already returns a session, so this is for clients that hold a "
        "short-lived access token and need their own refresh chain (for example "
        "the Swagger OAuth2 password flow)."
    ),
)
async def create_session(
    request: Request,
    user: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
):
    issued = await AuthService(session).issue_session(
        user,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        request_id=request_id(request),
    )
    return _issued(issued)


@router.post(
    "/session/refresh",
    response_model=SessionIssuedResponse,
    summary="Refresh browser session",
    description=(
        "Rotates the refresh token and returns a new access token. The presented "
        "refresh token becomes unusable; presenting it again is treated as replay "
        "and revokes every live session for that account. No access token is "
        "required — possession of the refresh token is the credential."
    ),
)
async def refresh_session(
    payload: RefreshSessionRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    throttle: AuthThrottle = Depends(get_auth_throttle),
):
    account = token_fingerprint(payload.refresh_token)
    await guard_throttle(throttle, request=request, account=account, scope="refresh")
    service = AuthService(session)
    try:
        issued = await service.refresh(
            payload.refresh_token,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=request_id(request),
        )
    except HTTPException:
        await record_throttle_failure(throttle, request=request, account=account, scope="refresh")
        raise
    await throttle.record_success(ip=client_ip(request), account=account, scope="refresh")
    return _issued(issued)


@router.delete("/session", response_model=MessageResponse, summary="Revoke browser session")
async def revoke_session(
    request: Request,
    payload: RefreshSessionRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Log out. Idempotent: an unknown or already-revoked token is not an error."""
    revoked = await AuthService(session).revoke_by_token(
        payload.refresh_token,
        ip_address=client_ip(request),
        request_id=request_id(request),
    )
    return MessageResponse(message="Session revoked" if revoked else "Session already ended")


@router.get(
    "/sessions",
    response_model=list[SessionSummaryResponse],
    summary="List my active sessions",
    description="Signed-in devices for the caller. Revoked and expired sessions are omitted.",
)
async def list_sessions(
    request: Request,
    user: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
):
    summaries = await AuthService(session).list_sessions(user, current_session_id=current_session_id(request))
    return _summaries(summaries)


@router.delete(
    "/sessions",
    response_model=MessageResponse,
    summary="Log out everywhere",
    description="Revokes every live session of the caller, including the current one.",
)
async def revoke_all_sessions(
    request: Request,
    user: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
):
    revoked = await AuthService(session).revoke_all(
        user,
        reason="logout_all",
        ip_address=client_ip(request),
        request_id=request_id(request),
    )
    return MessageResponse(message="Signed out of all devices", revoked_sessions=revoked)


@router.delete("/sessions/{session_id}", response_model=MessageResponse, summary="Revoke one of my sessions")
async def revoke_own_session(
    request: Request,
    session_id: int,
    user: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
):
    revoked = await AuthService(session).revoke_session(user, session_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SESSION_ENDED)
    return MessageResponse(message="Device signed out", revoked_sessions=1)


@router.get("/session", response_model=SessionSummaryResponse, summary="Describe the current session")
async def describe_current_session(
    request: Request,
    user: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
):
    session_id = current_session_id(request)
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SESSION_ENDED)
    summaries = await AuthService(session).list_sessions(user, current_session_id=session_id)
    for summary in summaries:
        if summary.id == session_id:
            return SessionSummaryResponse(**vars(summary))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SESSION_ENDED)
