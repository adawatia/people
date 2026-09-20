"""Rotating refresh sessions for the browser/API authentication lifecycle."""

from datetime import timedelta
import hashlib
import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from core.auth import fastapi_users
from core.database import get_async_session
from core.settings import get_settings
from db.models import AuthSession, User, now_ist

router = APIRouter(prefix="/auth/session", tags=["auth-session"])
settings = get_settings()
REFRESH_DAYS = 30


class RefreshSessionRequest(BaseModel):
    refresh_token: str = Field(..., description="Opaque refresh token returned by session creation")
    model_config = {"json_schema_extra": {"example": {"refresh_token": "replace-with-refresh-token"}}}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _access_token(user: User) -> str:
    now = now_ist()
    payload = {
        "sub": str(user.id),
        "aud": ["fastapi-users:auth"],
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create browser session", description="Exchange the short-lived bearer token from login for an access token and rotating refresh token.")
async def create_session(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
):
    raw_token = secrets.token_urlsafe(48)
    session.add(AuthSession(
        user_id=user.id,
        token_hash=_hash(raw_token),
        expires_at=now_ist() + timedelta(days=REFRESH_DAYS),
    ))
    await session.commit()
    return {"access_token": _access_token(user), "refresh_token": raw_token, "token_type": "bearer", "expires_in": 900}


@router.post("/refresh", summary="Refresh browser session", description="Rotates the refresh token. The previous refresh token cannot be reused.")
async def refresh_session(
    payload: RefreshSessionRequest,
    session: AsyncSession = Depends(get_async_session),
):
    raw_token = payload.refresh_token
    auth_session = await session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(raw_token)))
    now = now_ist()
    if not auth_session or auth_session.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    if auth_session.revoked_at:
        # A rotated token being presented again indicates replay. Kill the
        # account's remaining refresh sessions as a defensive response.
        await session.execute(update(AuthSession).where(
            AuthSession.user_id == auth_session.user_id,
            AuthSession.revoked_at.is_(None),
        ).values(revoked_at=now))
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token reuse detected")

    user = await session.get(User, auth_session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive")

    replacement_raw = secrets.token_urlsafe(48)
    replacement = AuthSession(
        user_id=user.id,
        token_hash=_hash(replacement_raw),
        expires_at=now + timedelta(days=REFRESH_DAYS),
    )
    session.add(replacement)
    await session.flush()
    auth_session.revoked_at = now
    auth_session.last_used_at = now
    auth_session.replaced_by_id = replacement.id
    await session.commit()
    return {"access_token": _access_token(user), "refresh_token": replacement_raw, "token_type": "bearer", "expires_in": 900}


@router.delete("", summary="Revoke browser session", description="Revokes the supplied refresh token and ends the browser session.")
async def revoke_session(
    payload: RefreshSessionRequest,
    session: AsyncSession = Depends(get_async_session),
):
    auth_session = await session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(payload.refresh_token)))
    if auth_session and auth_session.revoked_at is None:
        auth_session.revoked_at = now_ist()
        await session.commit()
    return {"message": "Session revoked"}
