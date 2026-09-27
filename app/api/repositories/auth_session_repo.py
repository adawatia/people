"""Persistence primitives for rotating refresh sessions.

The only subtle part is ``rotate``: two concurrent requests may present the same
refresh token, and exactly one of them may win.  Instead of reading the row and
deciding in Python (which races), the rotation is a single conditional UPDATE —
``WHERE id = :id AND revoked_at IS NULL`` — so the database decides the winner.
The loser sees ``rowcount == 0`` and is handled as a replay by the service.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuthSession


class AuthSessionRepository:
    """All ``auth_sessions`` access; no lifecycle policy lives here."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        absolute_expires_at: datetime,
        mfa_verified_at: datetime | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuthSession:
        """Insert a session row and flush so its id is available."""
        auth_session = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
            last_used_at=None,
            mfa_verified_at=mfa_verified_at,
            ip_address=(ip_address or None) and ip_address[:64],
            user_agent=(user_agent or None) and user_agent[:255],
        )
        self.session.add(auth_session)
        await self.session.flush()
        return auth_session

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return await self.session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))

    async def get_by_id(self, session_id: int) -> AuthSession | None:
        return await self.session.get(AuthSession, session_id)

    async def rotate(self, *, session_id: int, replacement_id: int, now: datetime) -> bool:
        """Atomically consume a live session; ``False`` means somebody else won."""

        result = await self.session.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(
                revoked_at=now,
                revoked_reason="rotated",
                last_used_at=now,
                replaced_by_id=replacement_id,
            )
        )
        return result.rowcount == 1

    async def revoke(self, *, session_id: int, now: datetime, reason: str) -> bool:
        """Revoke one session if it is still live (idempotent)."""

        result = await self.session.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
        )
        return result.rowcount == 1

    async def revoke_all_for_user(self, *, user_id: int, now: datetime, reason: str) -> int:
        """Revoke every live session for a user; returns how many were live."""

        result = await self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
        )
        return int(result.rowcount or 0)

    async def list_for_user(self, *, user_id: int, include_inactive: bool = False) -> list[AuthSession]:
        """Sessions of one user, newest first (for the signed-in-device list)."""

        statement = select(AuthSession).where(AuthSession.user_id == user_id)
        if not include_inactive:
            statement = statement.where(AuthSession.revoked_at.is_(None))
        statement = statement.order_by(AuthSession.created_at.desc(), AuthSession.id.desc())
        return list(await self.session.scalars(statement))

    async def count_active_for_user(self, *, user_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            )
            or 0
        )
