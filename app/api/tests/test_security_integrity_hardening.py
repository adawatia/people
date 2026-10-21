import asyncio
import hashlib
import hmac
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from starlette.requests import Request

from core import erp_auth
from core.auth import TECHNICAL_ADMIN_PERMISSIONS, current_business_user, get_user_permissions
from core.database import async_session_maker
from core.employee_access import EmployeeAccessScope
from core.erp_auth import ErpPrincipal, authenticate_erp_client, require_erp_scope
from core.erp_nonce_store import NonceStore, set_global_nonce_store
from db.models import Notification, NotificationReceipt, Shift, User
from repositories.notification_repo import NotificationRepository
from schemas.shifts import ShiftCreate
from services.shift_service import ShiftService


def _request(method: str, path: str, body: bytes = b"") -> Request:
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("test", 443),
            "state": {"request_id": "test-request"},
        },
        receive,
    )


def _signature(secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes = b"") -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_erp_hmac_authentication_enforces_scope_and_nonce_replay(monkeypatch):
    secret = "a" * 32
    settings = SimpleNamespace(
        is_development=False,
        erp_api_key="",
        erp_api_clients=json.dumps({"attendance": {"secret": secret, "scopes": ["attendance:write"]}}),
        erp_signature_max_age_seconds=300,
        auth_throttle_backend="memory",
    )
    monkeypatch.setattr(erp_auth, "get_settings", lambda: settings)
    monkeypatch.setattr(erp_auth, "record_audit_event", AsyncMock())
    # Nonces moved out of erp_auth into core.erp_nonce_store; reset the global
    # store so a nonce from another test cannot look like a replay here.
    set_global_nonce_store(NonceStore())
    timestamp = str(int(time.time()))
    nonce = "unique-nonce-12345"
    path = "/api/v1/integrations/erp/attendance"
    signature = _signature(secret, "POST", path, timestamp, nonce)

    principal = await authenticate_erp_client(
        _request("POST", path),
        legacy_key=None,
        client_id="attendance",
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
        session=AsyncMock(),
    )
    assert principal == ErpPrincipal("attendance", frozenset({"attendance:write"}))
    assert await require_erp_scope("attendance:write")(principal) == principal
    with pytest.raises(HTTPException) as denied:
        await require_erp_scope("employees:write")(principal)
    assert denied.value.status_code == 403

    with pytest.raises(HTTPException) as replay:
        await authenticate_erp_client(
            _request("POST", path),
            legacy_key=None,
            client_id="attendance",
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
            session=AsyncMock(),
        )
    assert replay.value.status_code == 409


@pytest.mark.asyncio
async def test_technical_admin_has_only_technical_permissions_and_no_business_entry():
    super_admin = SimpleNamespace(id=1, is_superuser=True, must_change_password=False)
    session = AsyncMock()
    assert set(await get_user_permissions(super_admin, session)) == TECHNICAL_ADMIN_PERMISSIONS
    session.scalar.assert_not_awaited()
    with pytest.raises(HTTPException) as denied:
        await current_business_user(super_admin, session)
    assert denied.value.detail["code"] == "TECHNICAL_ADMIN_ONLY"

    temporary_user = SimpleNamespace(id=2, is_superuser=False, must_change_password=True)
    with pytest.raises(HTTPException) as temporary:
        await current_business_user(temporary_user, session)
    assert temporary.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"


@pytest.mark.asyncio
async def test_broadcast_notification_read_state_is_per_user():
    suffix = uuid.uuid4().hex[:10]
    async with async_session_maker() as session:
        users = [
            User(
                username=f"receipt.{suffix}.{index}",
                email=f"receipt.{suffix}.{index}@example.test",
                hashed_password="unused",
                is_active=True,
            )
            for index in range(2)
        ]
        session.add_all(users)
        await session.flush()
        notification = Notification(
            title=f"Receipt {suffix}",
            message="Shared broadcast",
            notification_type="system",
            target_role="ALL",
        )
        session.add(notification)
        await session.flush()
        repo = NotificationRepository(session)
        audience = Notification.notification_id == notification.notification_id

        assert await repo.unread_count(audience, users[0].id) == 1
        assert await repo.unread_count(audience, users[1].id) == 1
        await repo.mark_read(notification.notification_id, users[0].id)
        await session.commit()

        assert await repo.unread_count(audience, users[0].id) == 0
        assert await repo.unread_count(audience, users[1].id) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(NotificationReceipt)
                .where(NotificationReceipt.notification_id == notification.notification_id)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_shift_erp_upsert_is_idempotent_and_atomic():
    suffix = uuid.uuid4().hex[:10]
    erp_id = f"shift-{suffix}"

    async def create_or_update(name: str):
        async with async_session_maker() as worker_session:
            return await ShiftService(worker_session).upsert_shift(
                erp_id,
                ShiftCreate(name=name, code=f"M{suffix}", start_time="09:00", end_time="18:00"),
            )

    first, second = await asyncio.gather(
        create_or_update(f"Morning {suffix}"),
        create_or_update(f"Concurrent {suffix}"),
    )
    assert first.id == second.id

    async with async_session_maker() as session:
        service = ShiftService(session)
        updated = await service.upsert_shift(
            erp_id,
            ShiftCreate(name=f"Updated {suffix}", code=f"M{suffix}", start_time="08:30", end_time="17:30"),
        )
        assert updated.id == first.id
        assert updated.name == f"Updated {suffix}"
        assert await session.scalar(select(func.count()).select_from(Shift).where(Shift.erp_id == erp_id)) == 1


def test_empty_workforce_scope_does_not_allow_any_employee():
    scope = EmployeeAccessScope()
    assert scope.allows(SimpleNamespace(id=1, unit_id=1, department_id=1)) is False
