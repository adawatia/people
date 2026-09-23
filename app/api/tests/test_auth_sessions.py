"""Refresh-session lifecycle: rotation, replay, expiry limits, logout.

Covers the security-critical invariants of the rotating refresh design:

* a refresh token is single-use and is replaced on every refresh;
* presenting a rotated token again is treated as replay and ends the chain;
* a session cannot outlive its idle or absolute limits, however often it rotates;
* logout is idempotent and only ends the session it names.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from core.database import async_session_maker, auth_engine
from core.settings import get_settings
from db.models import AuthSession, User, now_ist
from services.auth_service import AuditAction, AuthService
from tests.auth_helpers import (
    API,
    bearer,
    client,
    create_account,
    ensure_org_structure,
    login,
    refresh,
    run_async,
)

settings = get_settings()


@pytest.fixture
def unique_suffix() -> Iterator[str]:
    """Unique label per test so seeded rows never collide."""
    yield uuid.uuid4().hex[:6]


def _login_and_get(client_instance, identity: str):
    response = login(client_instance, identity)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("access_token") and payload.get("refresh_token"), payload
    return payload


def test_business_login_issues_a_session_directly(unique_suffix):
    async def _seed():
        async with async_session_maker() as session:
            unit, department, _ = (await ensure_org_structure(session, unique_suffix))[1:]
            user, _employee = await create_account(
                session, suffix=unique_suffix, unit_id=unit.id, department_id=department.id
            )
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        payload = _login_and_get(instance, user.username)

        # The access token is a short-lived, session-scoped bearer token — and it
        # is accepted by the normal API, unlike the old 8-hour exchange JWT which
        # no longer exists.
        claims = jwt.decode(payload["access_token"], settings.jwt_secret, algorithms=["HS256"], audience="fastapi-users:auth")
        assert claims["typ"] == "access"
        assert claims["sid"] == payload["session_id"]
        assert claims["exp"] - claims["iat"] == settings.access_token_ttl_seconds

        me = instance.get(f"{API}/users/me", headers=bearer(payload["access_token"]))
        assert me.status_code == 200, me.text


def test_refresh_rotates_and_old_token_is_rejected(unique_suffix):
    async def _seed():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        first = _login_and_get(instance, user.username)

        rotated = refresh(instance, first["refresh_token"])
        assert rotated.status_code == 200, rotated.text
        second = rotated.json()
        assert second["refresh_token"] != first["refresh_token"]
        assert second["access_token"] != first["access_token"]
        assert second["refresh_expires_at"] != first["refresh_expires_at"]

        # Old token: replay → 401 and the whole chain is revoked.
        replay = refresh(instance, first["refresh_token"])
        assert replay.status_code == 401
        assert "reuse" in replay.json()["detail"].lower()

        # The successor was revoked too, so the stolen chain cannot be used.
        assert refresh(instance, second["refresh_token"]).status_code == 401


def test_replay_of_a_logged_out_token_does_not_destroy_other_sessions(unique_suffix):
    """A revoked-but-not-rotated token is a logout, not a compromise signal."""

    async def _seed():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        first = _login_and_get(instance, user.username)
        second = _login_and_get(instance, user.username)
        assert first["session_id"] != second["session_id"]

        logout = instance.request(
            "DELETE", f"{API}/auth/session", json={"refresh_token": first["refresh_token"]}
        )
        assert logout.status_code == 200, logout.text

        # Idempotent, and the token reports a plain ended session.
        again = instance.request("DELETE", f"{API}/auth/session", json={"refresh_token": first["refresh_token"]})
        assert again.status_code == 200
        assert "already" in again.json()["message"].lower()
        assert refresh(instance, first["refresh_token"]).status_code == 401

        # The other device is untouched.
        assert refresh(instance, second["refresh_token"]).status_code == 200


def test_logout_all_devices_revokes_every_session(unique_suffix):
    async def _seed():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        first = _login_and_get(instance, user.username)
        second = _login_and_get(instance, user.username)

        revoke_all = instance.request("DELETE", f"{API}/auth/sessions", headers=bearer(first["access_token"]))
        assert revoke_all.status_code == 200, revoke_all.text
        assert revoke_all.json()["revoked_sessions"] >= 2

        assert refresh(instance, first["refresh_token"]).status_code == 401
        assert refresh(instance, second["refresh_token"]).status_code == 401


def test_sessions_endpoint_lists_devices_and_marks_the_current_one(unique_suffix):
    async def _seed():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        first = _login_and_get(instance, user.username)
        _login_and_get(instance, user.username)

        listing = instance.get(f"{API}/auth/sessions", headers=bearer(first["access_token"]))
        assert listing.status_code == 200, listing.text
        sessions = listing.json()
        assert len(sessions) == 2
        current = [item for item in sessions if item["is_current"]]
        assert len(current) == 1 and current[0]["id"] == first["session_id"]

        # And one device can be revoked by id.
        other = next(item for item in sessions if not item["is_current"])
        revoked = instance.request(
            "DELETE", f"{API}/auth/sessions/{other['id']}", headers=bearer(first["access_token"])
        )
        assert revoked.status_code == 200, revoked.text
        assert len(instance.get(f"{API}/auth/sessions", headers=bearer(first["access_token"])).json()) == 1


def test_idle_timeout_ends_the_session_and_blocks_refresh(unique_suffix):
    async def _seed():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        payload = _login_and_get(instance, user.username)
        stale = now_ist() - timedelta(seconds=settings.session_idle_timeout_seconds + 60)

        async def _age_session():
            async with async_session_maker() as session:
                row = await session.scalar(select(AuthSession).where(AuthSession.id == payload["session_id"]))
                row.last_used_at = stale
                row.created_at = stale
                await session.commit()
                await auth_engine.dispose()

        run_async(_age_session())

        denied = refresh(instance, payload["refresh_token"])
        assert denied.status_code == 401
        assert "inactivity" in denied.json()["detail"].lower()

        async def _session_state():
            async with async_session_maker() as session:
                row = await session.scalar(select(AuthSession).where(AuthSession.id == payload["session_id"]))
                state = (row.revoked_reason, row.revoked_at)
                await auth_engine.dispose()
                return state

        reason, revoked_at = run_async(_session_state())
        assert reason == "idle_timeout" and revoked_at is not None


def test_absolute_timeout_cannot_be_extended_by_refreshing(unique_suffix):
    """A long-lived chain still dies at its absolute deadline."""

    async def _seed():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        payload = _login_and_get(instance, user.username)

        rotated = refresh(instance, payload["refresh_token"])
        assert rotated.status_code == 200
        rotated_payload = rotated.json()

        async def _roll_back_the_absolute_deadline():
            """Simulate a session that has lived past its absolute limit."""
            async with async_session_maker() as session:
                row = await session.scalar(
                    select(AuthSession).where(AuthSession.id == rotated_payload["session_id"])
                )
                assert row is not None and row.revoked_at is None
                row.absolute_expires_at = now_ist() - timedelta(seconds=1)
                await session.commit()
                await auth_engine.dispose()

        run_async(_roll_back_the_absolute_deadline())

        denied = refresh(instance, rotated_payload["refresh_token"])
        assert denied.status_code == 401


def test_refresh_ttl_expiry_is_rejected(unique_suffix):
    async def _seed():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        payload = _login_and_get(instance, user.username)

        async def _expire():
            async with async_session_maker() as session:
                row = await session.scalar(select(AuthSession).where(AuthSession.id == payload["session_id"]))
                row.expires_at = now_ist() - timedelta(seconds=1)
                await session.commit()
                await auth_engine.dispose()

        run_async(_expire())
        assert refresh(instance, payload["refresh_token"]).status_code == 401


def test_concurrent_refresh_lets_exactly_one_request_win(unique_suffix):
    """Two parallel refreshes must not both mint descendants of one token."""

    async def _seed_and_refresh():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
        async with async_session_maker() as session:
            issued = await AuthService(session).issue_session(user)
        await auth_engine.dispose()
        return issued

    issued = run_async(_seed_and_refresh())

    async def _race():
        async def attempt():
            async with async_session_maker() as session:
                try:
                    return await AuthService(session).refresh(issued.refresh_token)
                except HTTPException as exc:
                    return exc

        first, second = await asyncio.gather(attempt(), attempt())
        await auth_engine.dispose()
        return first, second

    first, second = run_async(_race())
    winners = [result for result in (first, second) if not isinstance(result, HTTPException)]
    losers = [result for result in (first, second) if isinstance(result, HTTPException)]
    assert len(winners) == 1, (first, second)
    assert len(losers) == 1
    assert losers[0].status_code == 401

    async def _live_sessions():
        async with async_session_maker() as session:
            user = await session.scalar(select(User).where(User.username.like(f"%{unique_suffix}%")))
            rows = list(await session.scalars(select(AuthSession).where(AuthSession.user_id == user.id)))
            await auth_engine.dispose()
            return rows

    rows = run_async(_live_sessions())
    # Exactly one rotation happened: the winner's session, its revoked parent, and
    # the loser's rolled-back insert is gone. Nothing may remain live after a
    # detected concurrent replay.
    assert sum(1 for row in rows if row.revoked_at is None) == 0
    assert all(row.absolute_expires_at is not None for row in rows)


def test_reuse_detection_is_audited(unique_suffix):
    async def _seed():
        async with async_session_maker() as session:
            user, _ = await create_account(session, suffix=unique_suffix)
            await auth_engine.dispose()
            return user

    user = run_async(_seed())

    with client() as instance:
        payload = _login_and_get(instance, user.username)
        rotated = refresh(instance, payload["refresh_token"]).json()
        assert refresh(instance, payload["refresh_token"]).status_code == 401

        async def _events():
            from db.models import AuditLog

            async with async_session_maker() as session:
                rows = list(
                    await session.scalars(
                        select(AuditLog).where(AuditLog.action == AuditAction.REFRESH_REUSE_DETECTED)
                    )
                )
                await auth_engine.dispose()
                return rows

        events = run_async(_events())
        assert events, "reuse must write an audit event"
        # The event names the affected account and how many sessions were killed.
        assert any(
            str(user.id) in (event.filters_json or "") and "revoked_sessions" in (event.filters_json or "")
            for event in events
        )
        # The successor token was killed by the same event.
        assert refresh(instance, rotated["refresh_token"]).status_code == 401


@pytest.mark.parametrize("wrong", ["", "not-a-token", "a" * 64])
def test_malformed_refresh_tokens_get_a_401(unique_suffix, wrong):
    response = refresh(client(), wrong)
    assert response.status_code in {401, 422}
