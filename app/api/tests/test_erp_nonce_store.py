"""Tests for the ERP nonce store.

These tests require a PostgreSQL test database (DATABASE_URL ending in _test)
because they import the FastAPI app lifespan machinery.  They do NOT require
Redis: the in-memory backend is used automatically in development/test when no
shared client is wired.

Redis-backed behaviour can be verified separately against a real Redis instance.
"""
from __future__ import annotations

import asyncio
import selectors
import sys

import pytest

from core.erp_nonce_store import NonceStore, NonceStoreError, get_global_nonce_store


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def test_in_memory_nonce_accepts_once_per_pair():
    async def _test():
        store = NonceStore()
        assert await store.consume("client-a", "nonce-1", ttl_seconds=60) is True
        assert await store.consume("client-a", "nonce-1", ttl_seconds=60) is False
        assert await store.consume("client-a", "nonce-2", ttl_seconds=60) is True
        assert await store.consume("client-b", "nonce-1", ttl_seconds=60) is True

    run_async(_test())


def test_in_memory_nonce_expires():
    async def _test():
        store = NonceStore()
        assert await store.consume("client-a", "nonce-1", ttl_seconds=1) is True
        assert await store.consume("client-a", "nonce-1", ttl_seconds=1) is False
        await asyncio.sleep(1.2)
        # After expiry the same nonce may be reused.
        assert await store.consume("client-a", "nonce-1", ttl_seconds=1) is True

    run_async(_test())


def test_concurrent_in_memory_nonce_only_one_wins():
    async def _test():
        store = NonceStore()

        async def try_consume(tag):
            return await store.consume("client-a", "shared-nonce", ttl_seconds=60)

        # Two concurrent consumers racing for the same nonce.  Exactly one must
        # win even though the in-memory path is lock-based (correct for one
        # process; not sufficient across workers — that is why production uses
        # Redis SET NX EX).
        results = await asyncio.gather(
            asyncio.create_task(try_consume("first")),
            asyncio.create_task(try_consume("second")),
        )
        assert results.count(True) == 1
        assert results.count(False) == 1

    run_async(_test())


def test_production_store_fails_closed_without_redis():
    async def _test():
        store = NonceStore()
        store.configure_production(redis=None)  # simulate Redis unavailable
        with pytest.raises(NonceStoreError, match="requires Redis"):
            await store.consume("client-a", "nonce-1", ttl_seconds=60)

    run_async(_test())


def test_global_store_is_isolated_per_process():
    async def _test():
        # Reset the module-level singleton to a fresh in-memory store so the
        # test is deterministic regardless of import order.
        import core.erp_nonce_store as ns

        ns._global_store = NonceStore()
        try:
            a = get_global_nonce_store()
            assert await a.consume("client-x", "nonce-1", ttl_seconds=60) is True
            assert await a.consume("client-x", "nonce-1", ttl_seconds=60) is False
        finally:
            ns._global_store = None

    run_async(_test())
