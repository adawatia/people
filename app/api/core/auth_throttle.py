"""Authentication-specific throttling for login and refresh attempts.

The generic API limiter (``core/auth.py``) counts requests per IP.  That is the
wrong shape for authentication: one employee behind a corporate NAT must not be
able to lock everyone else out, and an attacker rotating IPs must still be
stopped by the account they are attacking.  So a failed attempt is recorded
against three keys — the source IP, the account, and the pair — and the
*strictest* verdict wins.

Policy shape (progressive, never permanent):

    attempts < warn_after            → allow, no delay
    warn_after ≤ attempts < max      → allow, with a small progressive delay
    attempts ≥ max                   → block for block_seconds, doubling per
                                       extra failure up to max_block_seconds

Counters reset on successful authentication, so an ordinary typo costs nothing
and a legitimate user is never locked out permanently.

State lives behind ``ThrottleStore``.  The in-process store is correct for a
single worker and is the default; ``AUTH_THROTTLE_BACKEND=redis`` switches to a
shared store so limits hold across workers (required once you scale out).  The
Redis implementation imports ``redis.asyncio`` lazily: a deployment that asks
for Redis without the package installed fails loudly rather than silently
degrading to per-worker limits.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from core.settings import Settings, get_settings

logger = logging.getLogger("hrms.auth.throttle")


@dataclass(frozen=True)
class ThrottleRule:
    """How one key class (IP / account / pair) is throttled."""

    kind: str
    max_failures: int
    block_seconds: int
    max_block_seconds: int
    warn_after: int
    delay_step_seconds: float


@dataclass(frozen=True)
class ThrottleDecision:
    """Verdict for one attempt."""

    allowed: bool
    retry_after_seconds: int = 0
    delay_seconds: float = 0.0
    reason: str | None = None
    kind: str | None = None


def _rules(settings: Settings, *, scope: str) -> tuple[ThrottleRule, ...]:
    """Failure budgets per key class.

    Deliberate asymmetry between the three keys:

    * ``ip_account`` is strict — it is the pairing that identifies an actual
      attack on an actual account, and it cannot deny service to anyone else.
    * ``account`` is looser — it protects a known employee from a distributed
      attack, but blocking on the account alone is the one key an outsider could
      weaponise, so it engages later and never for long.
    * ``ip`` is by far the loosest — many employees legitimately share an office
      NAT, so it only catches extreme spraying from a single address.

    No rule ever blocks permanently: the block doubles per extra failure and is
    capped, and any successful authentication clears all three counters.
    """
    base_max = (
        settings.auth_throttle_max_failures
        if scope == "login"
        else settings.auth_refresh_max_failures
    )
    return (
        ThrottleRule(
            kind="ip_account",
            max_failures=base_max,
            block_seconds=settings.auth_throttle_block_seconds,
            max_block_seconds=settings.auth_throttle_max_block_seconds,
            warn_after=max(1, base_max - 2),
            delay_step_seconds=0.5,
        ),
        ThrottleRule(
            kind="account",
            max_failures=base_max * 2,
            block_seconds=settings.auth_throttle_block_seconds * 2,
            max_block_seconds=min(settings.auth_throttle_max_block_seconds, 900),
            warn_after=base_max,
            delay_step_seconds=0.5,
        ),
        ThrottleRule(
            kind="ip",
            max_failures=base_max * 20,
            block_seconds=settings.auth_throttle_block_seconds,
            max_block_seconds=min(settings.auth_throttle_max_block_seconds, 900),
            warn_after=base_max * 10,
            delay_step_seconds=0.25,
        ),
    )


class ThrottleStore(Protocol):
    """Minimal counter/block store (implemented in-memory and on Redis)."""

    async def increment(self, key: str, *, window_seconds: int) -> int: ...

    async def count(self, key: str, *, window_seconds: int) -> int: ...

    async def clear(self, key: str) -> None: ...

    async def block(self, key: str, *, seconds: int) -> None: ...

    async def blocked_for(self, key: str) -> int: ...

    def describe(self) -> str: ...


class InMemoryThrottleStore:
    """Process-local store: fine for one worker, useless for two."""

    def __init__(self) -> None:
        self._counters: dict[str, tuple[int, float]] = {}
        self._blocks: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def describe(self) -> str:
        return "memory"

    def _prune(self, now: float) -> None:
        for key, (_, expires_at) in list(self._counters.items()):
            if expires_at <= now:
                del self._counters[key]
        for key, expires_at in list(self._blocks.items()):
            if expires_at <= now:
                del self._blocks[key]

    async def increment(self, key: str, *, window_seconds: int) -> int:
        now = time.monotonic()
        async with self._lock:
            self._prune(now)
            count, expires_at = self._counters.get(key, (0, now + window_seconds))
            if expires_at <= now:
                count, expires_at = 0, now + window_seconds
            count += 1
            self._counters[key] = (count, expires_at)
            return count

    async def count(self, key: str, *, window_seconds: int) -> int:
        now = time.monotonic()
        async with self._lock:
            self._prune(now)
            count, expires_at = self._counters.get(key, (0, 0.0))
            return count if expires_at > now else 0

    async def clear(self, key: str) -> None:
        async with self._lock:
            self._counters.pop(key, None)
            self._blocks.pop(key, None)

    async def block(self, key: str, *, seconds: int) -> None:
        now = time.monotonic()
        async with self._lock:
            self._blocks[key] = max(self._blocks.get(key, 0.0), now + seconds)

    async def blocked_for(self, key: str) -> int:
        now = time.monotonic()
        async with self._lock:
            expires_at = self._blocks.get(key, 0.0)
            if expires_at <= now:
                self._blocks.pop(key, None)
                return 0
            return int(expires_at - now) + 1


class RedisThrottleStore:
    """Shared store for multi-worker deployments.

    ``redis`` is an optional dependency: importing it lazily keeps a
    single-worker install lean while still surfacing a clear error when a
    deployment explicitly configures Redis.
    """

    def __init__(self, url: str) -> None:
        try:
            from redis.asyncio import Redis
        except ImportError as exc:  # pragma: no cover - depends on install
            raise RuntimeError(
                "AUTH_THROTTLE_BACKEND=redis requires the 'redis' package (uv add redis)."
            ) from exc
        self._client = Redis.from_url(url, encoding="utf-8", decode_responses=True)

    def describe(self) -> str:
        return "redis"

    @staticmethod
    def _counter_key(key: str) -> str:
        return f"hrms:auth:throttle:count:{key}"

    @staticmethod
    def _block_key(key: str) -> str:
        return f"hrms:auth:throttle:block:{key}"

    async def increment(self, key: str, *, window_seconds: int) -> int:
        redis_key = self._counter_key(key)
        count = await self._client.incr(redis_key)
        if count == 1:
            await self._client.expire(redis_key, window_seconds)
        return int(count)

    async def count(self, key: str, *, window_seconds: int) -> int:
        value = await self._client.get(self._counter_key(key))
        return int(value or 0)

    async def clear(self, key: str) -> None:
        await self._client.delete(self._counter_key(key), self._block_key(key))

    async def block(self, key: str, *, seconds: int) -> None:
        await self._client.set(self._block_key(key), "1", ex=seconds)

    async def blocked_for(self, key: str) -> int:
        ttl = await self._client.ttl(self._block_key(key))
        return int(ttl) if ttl and ttl > 0 else 0


def build_store(settings: Settings) -> ThrottleStore:
    """Wire the configured store, warning when it is worker-local."""
    backend = settings.auth_throttle_backend.strip().lower()
    if backend == "redis":
        if not settings.redis_url:
            raise RuntimeError("AUTH_THROTTLE_BACKEND=redis requires REDIS_URL")
        return RedisThrottleStore(settings.redis_url)
    if backend != "memory":
        logger.warning("unknown AUTH_THROTTLE_BACKEND=%s; falling back to memory", backend)
    if not settings.is_development:
        logger.warning(
            "auth throttling uses in-process state: limits are per worker. "
            "Set AUTH_THROTTLE_BACKEND=redis before scaling horizontally."
        )
    return InMemoryThrottleStore()


class AuthThrottle:
    """Applies the per-key policy and returns the strictest verdict.

    One instance is shared process-wide (see ``get_auth_throttle``) because an
    in-process store is only meaningful if every request uses the same one.
    """

    def __init__(self, settings: Settings | None = None, store: ThrottleStore | None = None) -> None:
        self._settings = settings or get_settings()
        self._store = store or build_store(self._settings)

    @property
    def store(self) -> ThrottleStore:
        return self._store

    @staticmethod
    def account_key(identity: str) -> str:
        """Hash the account identifier: audit-friendly, and never store the raw value."""
        return hashlib.sha256(identity.strip().lower().encode("utf-8")).hexdigest()[:32]

    def _key(self, rule: ThrottleRule, *, ip: str | None, account: str | None) -> str | None:
        if rule.kind == "ip":
            return f"ip:{ip}" if ip else None
        if rule.kind == "account":
            return f"acct:{account}" if account else None
        if not ip or not account:
            return None
        return f"pair:{ip}:{account}"

    def _delay_for(self, rule: ThrottleRule, attempts: int) -> float:
        if attempts <= rule.warn_after:
            return 0.0
        return round((attempts - rule.warn_after) * rule.delay_step_seconds, 2)

    def _block_seconds_for(self, rule: ThrottleRule, attempts: int) -> int:
        over = max(0, attempts - rule.max_failures)
        return min(rule.block_seconds * (2 ** over), rule.max_block_seconds)

    async def check(
        self,
        *,
        ip: str | None,
        account: str | None,
        scope: str = "login",
    ) -> ThrottleDecision:
        """Verdict *before* spending resources on verification."""
        window = self._settings.auth_throttle_window_seconds
        strictest = ThrottleDecision(allowed=True)
        for rule in _rules(self._settings, scope=scope):
            key = self._key(rule, ip=ip, account=account)
            if key is None:
                continue
            blocked_for = await self._store.blocked_for(key)
            if blocked_for:
                return ThrottleDecision(
                    allowed=False,
                    retry_after_seconds=blocked_for,
                    reason="too_many_attempts",
                    kind=rule.kind,
                )
            attempts = await self._store.count(key, window_seconds=window)
            delay = self._delay_for(rule, attempts)
            if delay > strictest.delay_seconds:
                strictest = ThrottleDecision(allowed=True, delay_seconds=delay, kind=rule.kind)
        return strictest

    async def record_failure(
        self,
        *,
        ip: str | None,
        account: str | None,
        scope: str = "login",
    ) -> ThrottleDecision:
        """Count a failed attempt and return the (possibly blocking) verdict."""
        window = self._settings.auth_throttle_window_seconds
        strictest = ThrottleDecision(allowed=True)
        for rule in _rules(self._settings, scope=scope):
            key = self._key(rule, ip=ip, account=account)
            if key is None:
                continue
            attempts = await self._store.increment(key, window_seconds=window)
            if attempts >= rule.max_failures:
                seconds = self._block_seconds_for(rule, attempts)
                await self._store.block(key, seconds=seconds)
                return ThrottleDecision(
                    allowed=False,
                    retry_after_seconds=seconds,
                    reason="too_many_attempts",
                    kind=rule.kind,
                )
            delay = self._delay_for(rule, attempts)
            if delay > strictest.delay_seconds:
                strictest = ThrottleDecision(allowed=True, delay_seconds=delay, kind=rule.kind)
        return strictest

    async def record_success(self, *, ip: str | None, account: str | None, scope: str = "login") -> None:
        """Clear the counters that a successful authentication proves were typos."""
        for rule in _rules(self._settings, scope=scope):
            key = self._key(rule, ip=ip, account=account)
            if key is not None:
                await self._store.clear(key)

    async def apply_delay(self, decision: ThrottleDecision) -> None:
        """Sleep the progressive delay, capped so it cannot pin a worker."""
        if decision.delay_seconds > 0:
            await asyncio.sleep(min(decision.delay_seconds, 2.0))

    async def reset_all(self) -> None:
        """Clear every key (used by tests and administrative runbooks)."""
        store = self._store
        if isinstance(store, InMemoryThrottleStore):
            # Deliberate internal reset: used by tests and administrative runbooks.
            async with store._lock:
                store._counters.clear()
                store._blocks.clear()


@lru_cache(maxsize=1)
def get_auth_throttle() -> AuthThrottle:
    """Process-wide throttler (shared store, shared counters)."""
    return AuthThrottle()
