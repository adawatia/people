"""Shared, atomic nonce storage for ERP HMAC replay protection.

The ERP auth layer must reject a signed request exactly once across every
running API worker/instance.  A memory dict behind a per-call asyncio.Lock is
correct for a single process but invisible to sibling workers, so two identical
requests can both pass: one worker inserts the nonce, the other never sees it.

This module is the single place that decides *where* nonces live and *how* they
are consumed.  Callers only call `consume(client_id, nonce, ttl)` and get a
bool.  Two production requirements drive the design:

* **Atomicity:** insertion must be "set if absent with expiry" so two identical
  concurrent requests cannot both win.  Redis `SET key value NX EX ttl` is that
  primitive.  The in-memory path emulates it with a lock for development only.
* **Failure mode:** in production the store must refuse to accept a nonce when
  the backing store is unavailable, rather than silently treating every nonce as
  brand-new (which would let replays through).  Development is exempt because
  there is no shared store by default.

Lifecycle
---------
Production should create one shared Redis client and hand it to the store at
startup, then close it at shutdown.  The store keeps the client open for the
lifetime of the process.  Creating/closing a Redis connection per nonce check
was the previous behaviour and is both slower and racy at the pool level.

Development/testing without Redis continues to work: the in-memory backend is
used automatically when no shared client is supplied and the runtime is not
production.  In production the absence of a shared client is a startup error.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


class NonceStoreError(RuntimeError):
    """The nonce store cannot operate (production Redis unavailable, etc.)."""


class NonceStore:
    """Atomic single-use nonce consumption, backed by Redis or memory.

    Usage
    -----
    Production::

        store = NonceStore redis=...  # shared client from lifespan
        await store.consume("erp-client", "nonce-value", ttl_seconds=300)
        # → True the first time, False on any later attempt within ttl

    Development (no Redis)::

        store = NonceStore()  # falls back to in-memory, process-local
    """

    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis
        self._memory: dict[str, float] = {}
        self._memory_lock = asyncio.Lock()
        # Deliberately set by the application at startup when Redis is intended.
        # When None in production this is an error surfaced on first use.
        self._production: bool = False

    def configure_production(self, redis: Redis) -> None:
        """Install the shared Redis client for production use.

        Called once at startup.  Replacing a previously configured client is not
        supported while requests are in flight.
        """
        self._redis = redis
        self._production = True

    async def consume(self, client_id: str, nonce: str, ttl_seconds: int) -> bool:
        """Return True exactly once for a given (client_id, nonce) pair.

        The caller treats True as "accept the request" and False as "replay:
        reject with 409".  The nonce is unexpired for ``ttl_seconds`` from the
        first successful consume.
        """
        if self._production:
            if self._redis is None:
                raise NonceStoreError(
                    "ERP nonce replay protection requires Redis in production "
                    "(AUTH_THROTTLE_BACKEND=redis and a shared Redis client)."
                )
            key = f"hrms:erp:nonce:{client_id}:{nonce}"
            ok = await self._redis.set(key, "1", ex=ttl_seconds, nx=True)
            return bool(ok)

        if not self._redis is None:
            # A client was supplied but we are not marked production: use it.
            key = f"hrms:erp:nonce:{client_id}:{nonce}"
            ok = await self._redis.set(key, "1", ex=ttl_seconds, nx=True)
            return bool(ok)

        return await self._consume_memory(client_id, nonce, ttl_seconds)

    async def _consume_memory(self, client_id: str, nonce: str, ttl_seconds: int) -> bool:
        """Process-local nonce store.  Correct for a single worker only."""
        key = f"hrms:erp:nonce:{client_id}:{nonce}"
        now = time.monotonic()
        async with self._memory_lock:
            expired = [k for k, exp in self._memory.items() if exp <= now]
            for k in expired:
                del self._memory[k]
            if key in self._memory:
                return False
            self._memory[key] = now + ttl_seconds
            return True

    @property
    def backend(self) -> str:
        """Store actually in use, for the sync-status diagnostic."""
        return "redis" if self._redis is not None else "memory"

    @property
    def is_shared(self) -> bool:
        """True when replay protection is shared across API workers."""
        return self._redis is not None

    async def close(self) -> None:
        """Release the shared Redis client, if owned by the application lifecycle.

        The store does not own the client — the application does — but this is a
        convenience hook so the lifespan can close whatever client was wired in
        without knowing whether it was Redis or nothing.
        """
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            finally:
                self._redis = None


_global_store: NonceStore | None = None


def set_global_nonce_store(store: NonceStore) -> None:
    """Install the process-wide nonce store.

    The FastAPI lifespan builds one store (Redis-backed in production) and calls
    this once at startup so every ERP request shares it.  Without this the
    request path would fall back to its own in-memory store and production
    replay protection would silently be process-local.
    """
    global _global_store
    _global_store = store


def get_global_nonce_store() -> NonceStore:
    """Return the application-wide nonce store.

    In production this is wired once at startup from the FastAPI lifespan.
    Before that point (or in development without Redis) the returned store is a
    fresh in-memory instance.
    """
    # ``global`` is required: without it the assignment below makes
    # ``_global_store`` local to this function and the read raises
    # UnboundLocalError on the first call.
    global _global_store
    if _global_store is None:
        _global_store = NonceStore()
    return _global_store
