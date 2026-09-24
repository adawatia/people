"""Authentication and session lifecycle.

This module owns every session state transition, so no router has to reason
about token rotation, revocation or expiry:

    ACTIVE   --refresh-->  ROTATED (a replacement session exists)
    ACTIVE   --logout / password change / admin reset-->  REVOKED
    ACTIVE   --idle, absolute or refresh TTL exceeded-->  EXPIRED
    ROTATED presented again (not by the rotation itself) --> COMPROMISE
             --> every live session of that user is revoked

Every transition writes a structured security event through the existing
``audit_logs`` mechanism (``core.audit``).  Tokens themselves are never logged:
only ids, hashes-of-hashes (fingerprints) and failure categories.

Routers stay thin: they authenticate, call this service, and shape the response.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import add_audit_event
from core.secret_box import SecretBoxError, decrypt_secret, encrypt_secret, is_encrypted
from core.session_policy import SessionPolicy, is_privileged, policy_for
from core.settings import Settings, get_settings
from core.tokens import (
    MFA_CHALLENGE_AUDIENCE,
    MFA_CHALLENGE_PURPOSE,
    PASSWORD_RECOVERY_AUDIENCE,
    PASSWORD_RECOVERY_PURPOSE,
    create_access_token,
    create_mfa_challenge_token,
    create_password_recovery_token,
    decode_token,
    generate_refresh_token,
    hash_refresh_token,
    token_fingerprint,
)
from core.totp import (
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    is_totp_replay,
    match_totp_step,
    provisioning_uri,
)
from db.models import User, now_ist
from repositories.auth_session_repo import AuthSessionRepository

logger = logging.getLogger("hrms.auth")

# Generic, enumeration-safe messages.  The specific reason lives in the audit
# event, never in the response body.
INVALID_CREDENTIALS = "Invalid login credentials"
SESSION_ENDED = "Your session has ended. Please sign in again."
REFRESH_REUSE = "Refresh token reuse detected"
# Distinguished from "invalid" so a spent code reads as a timing problem the user
# can act on, rather than looking like a typo they cannot fix.
TOTP_ALREADY_USED = "That code has already been used. Wait for the next code and try again."


class AuditAction:
    """Security event names written to ``audit_logs``."""

    LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    LOGIN_FAILED = "AUTH_LOGIN_FAILED"
    SUPER_ADMIN_LOGIN_SUCCESS = "SUPER_ADMIN_LOGIN_SUCCESS"
    SUPER_ADMIN_LOGIN_FAILED = "SUPER_ADMIN_LOGIN_FAILED"
    LOGOUT = "AUTH_LOGOUT"
    SESSION_CREATED = "AUTH_SESSION_CREATED"
    SESSION_REFRESHED = "AUTH_SESSION_REFRESHED"
    SESSION_REVOKED = "AUTH_SESSION_REVOKED"
    ALL_SESSIONS_REVOKED = "AUTH_ALL_SESSIONS_REVOKED"
    REFRESH_REUSE_DETECTED = "AUTH_REFRESH_REUSE_DETECTED"
    REFRESH_FAILED = "AUTH_REFRESH_FAILED"
    PASSWORD_CHANGED = "AUTH_PASSWORD_CHANGED"
    PASSWORD_RESET = "AUTH_PASSWORD_RESET"
    MFA_CHALLENGE = "AUTH_MFA_CHALLENGE"
    MFA_ENROLLED = "AUTH_MFA_ENROLLED"
    MFA_DISABLED = "AUTH_MFA_DISABLED"
    MFA_SUCCESS = "AUTH_MFA_SUCCESS"
    MFA_FAILED = "AUTH_MFA_FAILED"
    MFA_RECOVERY_REGENERATED = "AUTH_MFA_RECOVERY_REGENERATED"


@dataclass(frozen=True)
class IssuedSession:
    """The credential bundle returned to a trusted client (the BFF)."""

    access_token: str
    refresh_token: str
    access_expires_in: int
    session_id: int
    refresh_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(frozen=True)
class SessionSummary:
    """Non-secret view of a session, for the signed-in-device list."""

    id: int
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    absolute_expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    is_current: bool


@dataclass(frozen=True)
class MfaChallenge:
    """Second-factor challenge issued after a correct password."""

    token: str
    expires_in: int
    enrollment_required: bool


@dataclass(frozen=True)
class MfaVerification:
    """Outcome of a second-factor check.

    ``replayed`` is kept separate from a plain failure so the caller can tell a
    user to wait for the next code rather than to re-check one that was correct
    when it was issued.
    """

    ok: bool
    method: str | None = None
    replayed: bool = False


@dataclass(frozen=True)
class MfaEnrollment:
    """One-time view of a new authenticator secret (never returned again)."""

    secret: str
    otpauth_uri: str
    recovery_codes: list[str]


class AuthService:
    """Session lifecycle, MFA orchestration and authentication audit events."""

    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = AuthSessionRepository(session)

    # ── policy helpers ────────────────────────────────────────────────────────

    @staticmethod
    def policy_for_user(user: User) -> SessionPolicy:
        return policy_for(privileged=is_privileged(user))

    # ── audit helpers ─────────────────────────────────────────────────────────

    def _audit(
        self,
        *,
        actor: User | None,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        filters: dict[str, object] | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> None:
        add_audit_event(
            self.session,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            filters=filters,
            request_id=request_id,
            ip_address=ip_address,
        )

    async def record_login(
        self,
        *,
        user: User | None,
        identity: str,
        success: bool,
        privileged: bool,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Audit a login attempt (success or failure) and commit it standalone.

        Failures have no authenticated actor, so the account is recorded as a
        truncated hash of the submitted identity: enough to correlate an attack,
        not enough to enumerate accounts from the log.
        """
        if success and user is not None:
            action = AuditAction.SUPER_ADMIN_LOGIN_SUCCESS if privileged else AuditAction.LOGIN_SUCCESS
        else:
            action = AuditAction.SUPER_ADMIN_LOGIN_FAILED if privileged else AuditAction.LOGIN_FAILED
        self._audit(
            actor=user,
            action=action,
            entity_type="auth_login",
            entity_id=str(user.id) if user is not None else None,
            filters={
                "identity": token_fingerprint(identity.strip().lower()),
                "privileged": privileged,
                "reason": reason or ("ok" if success else "invalid_credentials"),
                "user_agent": (user_agent or "")[:200],
            },
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()

    # ── session lifecycle ─────────────────────────────────────────────────────

    async def issue_session(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        mfa_verified: bool = False,
        audit_action: str = AuditAction.SESSION_CREATED,
    ) -> IssuedSession:
        """Create a refresh session and return the access/refresh pair."""
        policy = self.policy_for_user(user)
        now = now_ist()
        raw_refresh = generate_refresh_token()
        created = await self.repo.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=policy.refresh_expiry(now),
            absolute_expires_at=policy.absolute_expiry(now),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._audit(
            actor=user,
            action=audit_action,
            entity_type="auth_session",
            entity_id=str(created.id),
            filters={
                "privileged": is_privileged(user),
                "mfa_verified": mfa_verified,
                "absolute_expires_at": created.absolute_expires_at,
            },
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()
        return IssuedSession(
            access_token=self._access_token(user, session_id=created.id, policy=policy, now=now),
            refresh_token=raw_refresh,
            access_expires_in=policy.access_token_ttl_seconds,
            session_id=created.id,
            refresh_expires_at=created.expires_at,
            absolute_expires_at=created.absolute_expires_at,
        )

    def _access_token(self, user: User, *, session_id: int, policy: SessionPolicy, now: datetime) -> str:
        return create_access_token(
            subject=user.id,
            secret=self.settings.jwt_secret,
            ttl_seconds=policy.access_token_ttl_seconds,
            now=now,
            session_id=session_id,
        )

    async def refresh(
        self,
        raw_token: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> IssuedSession:
        """Rotate a refresh token, enforcing idle and absolute lifetimes."""
        now = now_ist()
        fingerprint = token_fingerprint(raw_token)
        auth_session = await self.repo.get_by_token_hash(hash_refresh_token(raw_token))

        if auth_session is None:
            await self._refresh_denied(
                action=AuditAction.REFRESH_FAILED,
                reason="unknown_token",
                fingerprint=fingerprint,
                ip_address=ip_address,
                request_id=request_id,
            )

        if auth_session.expires_at <= now or auth_session.absolute_expires_at <= now:
            await self._refresh_denied(
                action=AuditAction.REFRESH_FAILED,
                reason="expired",
                fingerprint=fingerprint,
                ip_address=ip_address,
                request_id=request_id,
                session_id=auth_session.id,
                user_id=auth_session.user_id,
            )

        if auth_session.revoked_at is not None:
            if auth_session.replaced_by_id is not None:
                # A rotated token came back: treat as possible theft and end the
                # whole chain (the standard OAuth refresh-token reuse response).
                revoked = await self.repo.revoke_all_for_user(
                    user_id=auth_session.user_id, now=now, reason="reuse_detected"
                )
                self._audit(
                    actor=None,
                    action=AuditAction.REFRESH_REUSE_DETECTED,
                    entity_type="auth_session",
                    entity_id=str(auth_session.id),
                    filters={
                        "user_id": auth_session.user_id,
                        "fingerprint": fingerprint,
                        "revoked_sessions": revoked,
                    },
                    ip_address=ip_address,
                    request_id=request_id,
                )
                await self.session.commit()
                logger.warning(
                    "refresh token reuse detected",
                    extra={"event": "auth_refresh_reuse", "user_id": auth_session.user_id, "revoked": revoked},
                )
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFRESH_REUSE)

            # Revoked without a replacement: logout, password change or an admin
            # action.  Not a compromise signal, so do not cascade.
            await self._refresh_denied(
                action=AuditAction.REFRESH_FAILED,
                reason=f"revoked:{auth_session.revoked_reason or 'unknown'}",
                fingerprint=fingerprint,
                ip_address=ip_address,
                request_id=request_id,
                session_id=auth_session.id,
                user_id=auth_session.user_id,
            )

        user = await self.session.get(User, auth_session.user_id)
        if user is None or not user.is_active:
            await self.repo.revoke_all_for_user(user_id=auth_session.user_id, now=now, reason="account_inactive")
            await self.session.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_ENDED)

        policy = self.policy_for_user(user)
        last_seen = auth_session.last_used_at or auth_session.created_at
        if policy.idle_deadline(last_seen) <= now:
            await self.repo.revoke(session_id=auth_session.id, now=now, reason="idle_timeout")
            self._audit(
                actor=user,
                action=AuditAction.SESSION_REVOKED,
                entity_type="auth_session",
                entity_id=str(auth_session.id),
                filters={"reason": "idle_timeout", "idle_seconds": policy.idle_timeout_seconds},
                ip_address=ip_address,
                request_id=request_id,
            )
            await self.session.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired after inactivity")

        raw_replacement = generate_refresh_token()
        replacement = await self.repo.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_replacement),
            # A rotation inherits the chain's absolute deadline: refreshing must
            # never extend a session beyond its absolute lifetime.
            expires_at=min(policy.refresh_expiry(now), auth_session.absolute_expires_at),
            absolute_expires_at=auth_session.absolute_expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # Plain ids, captured while the mapped objects are still loaded: the
        # rollback below expires everything attached to this session.
        user_id = user.id
        claimed_session_id = auth_session.id
        rotated = await self.repo.rotate(session_id=claimed_session_id, replacement_id=replacement.id, now=now)
        if not rotated:
            # Another request consumed the same token first.  Roll back our
            # replacement and report replay: only one descendant may exist.
            await self.session.rollback()
            revoked = await self.repo.revoke_all_for_user(user_id=user_id, now=now, reason="reuse_detected")
            self._audit(
                actor=await self.session.get(User, user_id),
                action=AuditAction.REFRESH_REUSE_DETECTED,
                entity_type="auth_session",
                entity_id=str(claimed_session_id),
                filters={
                    "fingerprint": fingerprint,
                    "concurrent": True,
                    "revoked_sessions": revoked,
                },
                ip_address=ip_address,
                request_id=request_id,
            )
            await self.session.commit()
            logger.warning(
                "concurrent refresh detected; replay protection revoked the chain",
                extra={"event": "auth_refresh_reuse", "user_id": user_id, "revoked": revoked},
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFRESH_REUSE)

        self._audit(
            actor=user,
            action=AuditAction.SESSION_REFRESHED,
            entity_type="auth_session",
            entity_id=str(replacement.id),
            filters={"previous_session_id": auth_session.id, "privileged": is_privileged(user)},
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()
        return IssuedSession(
            access_token=self._access_token(user, session_id=replacement.id, policy=policy, now=now),
            refresh_token=raw_replacement,
            access_expires_in=policy.access_token_ttl_seconds,
            session_id=replacement.id,
            refresh_expires_at=replacement.expires_at,
            absolute_expires_at=replacement.absolute_expires_at,
        )

    async def _refresh_denied(
        self,
        *,
        action: str,
        reason: str,
        fingerprint: str,
        ip_address: str | None,
        request_id: str | None,
        session_id: int | None = None,
        user_id: int | None = None,
    ) -> NoReturn:
        """Audit and reject a refresh attempt.  Always raises."""
        self._audit(
            actor=None,
            action=action,
            entity_type="auth_session",
            entity_id=str(session_id) if session_id is not None else None,
            filters={"reason": reason, "fingerprint": fingerprint, "user_id": user_id},
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_ENDED)

    async def revoke_by_token(
        self,
        raw_token: str,
        *,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> bool:
        """Log out one session.  Idempotent: unknown tokens are not an error."""
        now = now_ist()
        auth_session = await self.repo.get_by_token_hash(hash_refresh_token(raw_token))
        if auth_session is None:
            return False
        revoked = await self.repo.revoke(session_id=auth_session.id, now=now, reason="logout")
        if revoked:
            user = await self.session.get(User, auth_session.user_id)
            self._audit(
                actor=user,
                action=AuditAction.LOGOUT,
                entity_type="auth_session",
                entity_id=str(auth_session.id),
                filters={"reason": "logout"},
                ip_address=ip_address,
                request_id=request_id,
            )
        await self.session.commit()
        return revoked

    async def revoke_session(self, user: User, session_id: int, *, reason: str = "user_revoked") -> bool:
        """Revoke one of the caller's own sessions (device management)."""
        auth_session = await self.repo.get_by_id(session_id)
        if auth_session is None or auth_session.user_id != user.id:
            return False
        revoked = await self.repo.revoke(session_id=session_id, now=now_ist(), reason=reason)
        if revoked:
            self._audit(
                actor=user,
                action=AuditAction.SESSION_REVOKED,
                entity_type="auth_session",
                entity_id=str(session_id),
                filters={"reason": reason},
            )
        await self.session.commit()
        return revoked

    async def revoke_all(
        self,
        user: User,
        *,
        reason: str,
        action: str = AuditAction.ALL_SESSIONS_REVOKED,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> int:
        """Revoke every live session of a user (logout-everywhere, password events)."""
        revoked = await self.repo.revoke_all_for_user(user_id=user.id, now=now_ist(), reason=reason)
        self._audit(
            actor=user,
            action=action,
            entity_type="user",
            entity_id=str(user.id),
            filters={"reason": reason, "revoked_sessions": revoked},
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()
        return revoked

    async def list_sessions(self, user: User, *, current_session_id: int | None = None) -> list[SessionSummary]:
        """Live sessions for the signed-in-device list, newest first."""
        rows = await self.repo.list_for_user(user_id=user.id)
        now = now_ist()
        return [
            SessionSummary(
                id=row.id,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
                expires_at=row.expires_at,
                absolute_expires_at=row.absolute_expires_at,
                ip_address=row.ip_address,
                user_agent=row.user_agent,
                is_current=row.id == current_session_id,
            )
            for row in rows
            if row.expires_at > now and row.absolute_expires_at > now
        ]

    # ── MFA ───────────────────────────────────────────────────────────────────

    def policy_requires_mfa(self, user: User) -> bool:
        """Whether this account's *policy* mandates a second factor."""
        return self.policy_for_user(user).mfa_required

    def mfa_required(self, user: User) -> bool:
        """Whether a second factor must be presented at sign-in.

        Either the policy demands one (privileged accounts by default) or the
        account has already enrolled a factor.  The second half matters: an
        enrolled authenticator is always used, otherwise opting into MFA from
        account settings would silently protect nothing.
        """
        return bool(self.settings.mfa_enabled and (user.mfa_enabled or self.policy_requires_mfa(user)))

    async def begin_mfa_challenge(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> MfaChallenge:
        """Issue the second-factor challenge after a successful password check."""
        now = now_ist()
        enrollment_required = not user.mfa_enabled or not user.mfa_secret
        ttl = self.settings.mfa_challenge_ttl_seconds
        token = create_mfa_challenge_token(
            subject=user.id,
            secret=self.settings.jwt_secret,
            ttl_seconds=ttl,
            now=now,
            enrollment_required=enrollment_required,
        )
        self._audit(
            actor=user,
            action=AuditAction.MFA_CHALLENGE,
            entity_type="user",
            entity_id=str(user.id),
            filters={"enrollment_required": enrollment_required, "user_agent": (user_agent or "")[:200]},
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()
        return MfaChallenge(token=token, expires_in=ttl, enrollment_required=enrollment_required)

    def resolve_mfa_challenge(self, challenge_token: str) -> tuple[User, bool]:
        """Validate a challenge token and return ``(user, enrollment_required)``.

        The challenge carries a dedicated audience, so it can never be used as an
        access token even though it is signed with the same key.
        """
        try:
            payload = decode_token(
                challenge_token, secret=self.settings.jwt_secret, audience=MFA_CHALLENGE_AUDIENCE
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Your verification window has expired. Sign in again."
            ) from exc
        if payload.get("typ") != MFA_CHALLENGE_PURPOSE:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification token")
        return int(payload["sub"]), bool(payload.get("enrol"))

    def create_password_recovery_challenge(self, user_id: int, *, recoverable: bool) -> str:
        """Create a uniform-shaped recovery-start token.

        The token is deliberately unusable unless the account exists and has an
        active factor. This avoids returning different response shapes for known
        and unknown identifiers.
        """
        import secrets

        return create_password_recovery_token(
            subject=user_id,
            secret=self.settings.jwt_secret,
            ttl_seconds=self.settings.password_recovery_ttl_seconds,
            now=now_ist(),
            recoverable=recoverable,
            nonce=secrets.token_urlsafe(24),
        )

    def resolve_password_recovery(self, token: str) -> tuple[int, str]:
        try:
            payload = decode_token(token, secret=self.settings.jwt_secret, audience=PASSWORD_RECOVERY_AUDIENCE)
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Recovery session expired") from exc
        if payload.get("typ") != PASSWORD_RECOVERY_PURPOSE or not payload.get("ok"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Recovery session is not valid")
        user_id = int(payload["sub"])
        nonce = str(payload.get("nonce") or "")
        if not nonce:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Recovery session is not valid")
        return user_id, nonce

    def _secret_key(self) -> str:
        return self.settings.mfa_secret_key()

    async def _active_secret(self, user: User) -> str | None:
        """The seed currently protecting the account (decrypted), if any."""
        if not user.mfa_secret:
            return None
        try:
            secret = decrypt_secret(user.mfa_secret, self._secret_key())
            if not is_encrypted(user.mfa_secret):
                # Legacy deployments stored the seed in plaintext. Upgrade it
                # opportunistically during the first successful read, without
                # requiring a risky bulk rewrite or exposing the seed in logs.
                user.mfa_secret = encrypt_secret(secret, self._secret_key())
                await self.session.flush()
            return secret
        except SecretBoxError:
            # Wrong key or tampered value. Fail closed rather than treating the
            # ciphertext as the seed: the account falls back to recovery codes
            # and re-enrolment instead of accepting codes derived from garbage.
            logger.warning(
                "stored MFA secret could not be decrypted",
                extra={"event": "mfa_secret_undecryptable", "user_id": user.id},
            )
            return None

    async def start_enrollment(self, user: User) -> MfaEnrollment:
        """Issue a TOTP secret for enrolment, plus recovery codes when new.

        The seed is written to ``mfa_pending_secret`` and nothing else changes: an
        account that already has a factor keeps it - and keeps needing it at
        sign-in - until the replacement is proven, so abandoning this flow can no
        longer disable a second factor or invalidate an authenticator the user is
        still holding.

        Recovery codes are issued only for a first factor.  Replacing a factor
        keeps the existing codes valid (regenerating them is a separate, explicit
        action) so a half-finished reset cannot invalidate codes the user wrote
        down and may need tomorrow.
        """
        secret = generate_secret()
        if user.mfa_pending_secret and user.mfa_pending_expires_at and user.mfa_pending_expires_at <= now_ist():
            user.mfa_pending_secret = None
            user.mfa_pending_expires_at = None
        user.mfa_pending_secret = encrypt_secret(secret, self._secret_key())
        user.mfa_pending_expires_at = now_ist() + timedelta(seconds=self.settings.mfa_pending_ttl_seconds)
        first_factor = not user.mfa_secret
        recovery_codes = generate_recovery_codes() if first_factor else []
        if first_factor:
            user.mfa_recovery_code_hashes = _encode_recovery_hashes(recovery_codes)
        account = user.username or user.email or str(user.id)
        await self.session.commit()
        return MfaEnrollment(
            secret=secret,
            otpauth_uri=provisioning_uri(secret=secret, account=account, issuer=self.settings.mfa_issuer),
            recovery_codes=recovery_codes,
        )

    async def regenerate_recovery_codes(self, user: User) -> list[str]:
        """Replace every recovery code with a fresh set (step-up protected)."""
        if not user.mfa_secret:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Set up an authenticator before generating recovery codes"
            )
        codes = generate_recovery_codes()
        user.mfa_recovery_code_hashes = _encode_recovery_hashes(codes)
        self._audit(
            actor=user,
            action=AuditAction.MFA_RECOVERY_REGENERATED,
            entity_type="user",
            entity_id=str(user.id),
            filters={"count": len(codes)},
        )
        await self.session.commit()
        return codes

    async def activate_enrollment(
        self,
        user: User,
        code: str,
        *,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Prove possession of the pending secret, then promote it to active.

        Proof comes first and the swap is atomic with it: the active seed, its
        replay counter and the recovery codes are only replaced once a code from
        the new authenticator has been accepted.
        """
        locked_user = await self.session.scalar(select(User).where(User.id == user.id).with_for_update())
        if locked_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_ENDED)
        user = locked_user
        pending = None
        if user.mfa_pending_secret:
            if user.mfa_pending_expires_at and user.mfa_pending_expires_at <= now_ist():
                user.mfa_pending_secret = None
                user.mfa_pending_expires_at = None
                await self.session.commit()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA enrolment expired; start again")
            try:
                pending = decrypt_secret(user.mfa_pending_secret, self._secret_key())
            except SecretBoxError:
                pending = None
        if not pending:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start MFA enrolment first")

        matched_step = match_totp_step(code, pending, now_ist())
        # The replay counter belongs to the active secret. A pending enrollment
        # is a different factor even though its TOTP counter has the same
        # time-based value. Comparing the pending code with the active secret's
        # counter rejects every replacement confirmed in the same 30-second
        # interval as the sign-in that opened Settings.
        if matched_step is None:
            self._audit(
                actor=user,
                action=AuditAction.MFA_FAILED,
                entity_type="user",
                entity_id=str(user.id),
                filters={"stage": "activate", "reason": "invalid"},
                ip_address=ip_address,
                request_id=request_id,
            )
            await self.session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That code is not valid. Check that your device time is set automatically and try the current code.",
            )

        user.mfa_secret = user.mfa_pending_secret
        user.mfa_pending_secret = None
        user.mfa_pending_expires_at = None
        user.mfa_enabled = True
        user.mfa_enrolled_at = now_ist()
        user.last_mfa_verified_at = now_ist()
        user.mfa_last_used_step = matched_step
        self._audit(
            actor=user,
            action=AuditAction.MFA_ENROLLED,
            entity_type="user",
            entity_id=str(user.id),
            filters={"method": "totp"},
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()

    async def verify_mfa(
        self,
        user: User,
        code: str,
        *,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> MfaVerification:
        """Verify a TOTP code or a single-use recovery code.

        A code is accepted once.  Having matched, its time step is recorded and
        the same step can never be accepted again, so an observed or intercepted
        code cannot be replayed for the rest of its validity (including the drift
        window either side of it).

        Returns *why* a submission failed, not just that it did: a spent code and
        a wrong one call for different advice ("wait for the next code" versus
        "check the code"), and collapsing them would send users hunting for a
        typing mistake that does not exist.
        """
        locked_user = await self.session.scalar(select(User).where(User.id == user.id).with_for_update())
        if locked_user is None:
            return MfaVerification(ok=False)
        user = locked_user
        submitted = (code or "").strip()
        secret = await self._active_secret(user)
        matched_step = match_totp_step(submitted, secret, now_ist()) if secret else None
        replayed = matched_step is not None and is_totp_replay(matched_step, user.mfa_last_used_step)

        # A TOTP match short-circuits: a recovery code is only consumed when the
        # app code did not match (or was already spent), so a valid code never
        # burns a single-use recovery code either.
        verified = matched_step is not None and not replayed
        used_recovery_code = False
        if not verified:
            used_recovery_code = await self._consume_recovery_code(user, submitted)
            verified = used_recovery_code

        if not verified:
            self._audit(
                actor=user,
                action=AuditAction.MFA_FAILED,
                entity_type="user",
                entity_id=str(user.id),
                filters={"stage": "verify", "reason": "replayed" if replayed else "invalid"},
                ip_address=ip_address,
                request_id=request_id,
            )
            await self.session.commit()
            return MfaVerification(ok=False, replayed=replayed)

        if matched_step is not None:
            user.mfa_last_used_step = matched_step
        user.last_mfa_verified_at = now_ist()
        method = "recovery_code" if used_recovery_code else "totp"
        self._audit(
            actor=user,
            action=AuditAction.MFA_SUCCESS,
            entity_type="user",
            entity_id=str(user.id),
            filters={"method": method},
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()
        return MfaVerification(ok=True, method=method)

    async def _consume_recovery_code(self, user: User, code: str) -> bool:
        """Redeem a recovery code, removing it so it cannot be reused."""
        if not code or not user.mfa_recovery_code_hashes:
            return False
        stored = _decode_recovery_hashes(user.mfa_recovery_code_hashes)
        candidate = hash_recovery_code(code)
        if candidate not in stored:
            return False
        stored.remove(candidate)
        user.mfa_recovery_code_hashes = _encode_recovery_hashes([], already_hashed=stored)
        await self.session.flush()
        return True

    async def issue_password_recovery_reset(self, user: User) -> str:
        """Persist a one-time password-reset capability after MFA succeeds."""
        import secrets

        raw = secrets.token_urlsafe(48)
        user.password_recovery_token_hash = hash_refresh_token(raw)
        user.password_recovery_expires_at = now_ist() + timedelta(seconds=self.settings.password_recovery_ttl_seconds)
        self._audit(
            actor=user,
            action="AUTH_PASSWORD_RECOVERY_VERIFIED",
            entity_type="user",
            entity_id=str(user.id),
            filters={"method": "mfa"},
        )
        await self.session.commit()
        return raw

    async def reset_password_with_token(self, raw_token: str, new_password_hash: str) -> User:
        """Consume a password reset token under a row lock and revoke sessions."""
        now = now_ist()
        user = await self.session.scalar(
            select(User)
            .where(
                User.password_recovery_token_hash == hash_refresh_token(raw_token),
                User.password_recovery_expires_at > now,
            )
            .with_for_update()
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Recovery session expired")
        user.hashed_password = new_password_hash
        user.must_change_password = False
        user.password_recovery_token_hash = None
        user.password_recovery_expires_at = None
        await self.revoke_all(
            user,
            reason="password_recovery",
            action=AuditAction.PASSWORD_RESET,
        )
        return user

    async def disable_mfa(self, user: User, *, ip_address: str | None = None, request_id: str | None = None) -> None:
        """Remove the second factor (requires a fresh password re-check upstream)."""
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_pending_secret = None
        user.mfa_pending_expires_at = None
        user.mfa_enrolled_at = None
        user.mfa_last_used_step = None
        user.mfa_recovery_code_hashes = None
        self._audit(
            actor=user,
            action=AuditAction.MFA_DISABLED,
            entity_type="user",
            entity_id=str(user.id),
            filters={},
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()


def _encode_recovery_hashes(codes: list[str], *, already_hashed: list[str] | None = None) -> str:
    hashes = list(already_hashed) if already_hashed is not None else [hash_recovery_code(code) for code in codes]
    return json.dumps(hashes)


def _decode_recovery_hashes(payload: str) -> list[str]:
    try:
        value = json.loads(payload)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []
