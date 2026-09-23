"""Session and token policy derived from configuration.

Every lifetime decision (access token TTL, refresh TTL, idle timeout, absolute
lifetime) is made here and nowhere else, so routers and services cannot drift
into hard-coded values and a deployment can tighten the policy in one place.

Two profiles exist:

    business   — an employee login (any business role)
    privileged — a Super Admin / technical account

Privileged sessions are deliberately shorter: a break-glass account should not
stay usable for a full working day, let alone 30 days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.settings import Settings, get_settings


@dataclass(frozen=True)
class SessionPolicy:
    """Resolved lifetimes for one authentication profile."""

    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int
    idle_timeout_seconds: int
    absolute_timeout_seconds: int
    mfa_required: bool

    def refresh_expiry(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self.refresh_token_ttl_seconds)

    def absolute_expiry(self, now: datetime) -> datetime:
        """The hard end of a session chain, however often it is refreshed."""
        return now + timedelta(seconds=self.absolute_timeout_seconds)

    def idle_deadline(self, last_used_at: datetime) -> datetime:
        return last_used_at + timedelta(seconds=self.idle_timeout_seconds)


def policy_for(*, privileged: bool, settings: Settings | None = None) -> SessionPolicy:
    """Return the policy for a business or privileged session.

    An idle timeout longer than the absolute lifetime is meaningless, so the
    absolute limit also caps the idle window; that keeps a misconfiguration from
    producing a session that can never go idle.
    """
    resolved = settings or get_settings()
    if privileged:
        idle = min(resolved.privileged_idle_timeout_seconds, resolved.privileged_absolute_timeout_seconds)
        return SessionPolicy(
            access_token_ttl_seconds=resolved.privileged_access_token_ttl_seconds,
            refresh_token_ttl_seconds=resolved.refresh_token_ttl_seconds,
            idle_timeout_seconds=idle,
            absolute_timeout_seconds=resolved.privileged_absolute_timeout_seconds,
            mfa_required=resolved.mfa_enabled and resolved.mfa_required_for_super_admin,
        )

    idle = min(resolved.session_idle_timeout_seconds, resolved.session_absolute_timeout_seconds)
    return SessionPolicy(
        access_token_ttl_seconds=resolved.access_token_ttl_seconds,
        refresh_token_ttl_seconds=resolved.refresh_token_ttl_seconds,
        idle_timeout_seconds=idle,
        absolute_timeout_seconds=resolved.session_absolute_timeout_seconds,
        mfa_required=False,
    )


def is_privileged(user: object) -> bool:
    """Privileged = technical Super Admin. Business roles are never privileged."""
    return bool(getattr(user, "is_superuser", False))
