from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

import services.user_admin_service as module
from db.models import now_ist
from services.auth_service import AuditAction
from services.user_admin_service import UserAdminService


def service_with_mocks():
    service = UserAdminService(Mock())
    service.repo = SimpleNamespace(get_workforce_user=AsyncMock())
    service.manager = SimpleNamespace(
        password_helper=SimpleNamespace(
            verify_and_update=Mock(return_value=(True, None)),
            hash=Mock(return_value="new-password-hash"),
        )
    )
    return service


def test_super_admin_step_up_requires_mfa_from_the_current_session(monkeypatch):
    service = service_with_mocks()
    actor = SimpleNamespace(
        is_superuser=True,
        hashed_password="admin-hash",
        mfa_enabled=True,
        last_mfa_verified_at=now_ist(),
    )
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            mfa_required_for_super_admin=True,
            sensitive_action_mfa_max_age_seconds=600,
        ),
    )

    with pytest.raises(HTTPException) as missing:
        service.verify_step_up(actor, "admin-password", session_mfa_verified_at=None)
    assert missing.value.detail["code"] == "RECENT_MFA_REQUIRED"

    service.verify_step_up(
        actor,
        "admin-password",
        session_mfa_verified_at=now_ist() - timedelta(seconds=30),
    )


@pytest.mark.asyncio
async def test_super_admin_account_directory_replaces_repository_rows_with_response_items():
    service = service_with_mocks()
    actor = SimpleNamespace(is_superuser=True)
    user = SimpleNamespace(
        id=8,
        username="demo.engineer",
        email="engineer@example.com",
        first_name="Demo",
        last_name="Engineer",
        mobile_number="987602206",
        is_active=True,
        is_verified=True,
        must_change_password=False,
        mfa_enabled=False,
        created_at=datetime.now(UTC),
    )
    employee = SimpleNamespace(id=12, employee_code="EMP-012", role="EMPLOYEE")
    service.repo.account_page = AsyncMock(
        return_value=(
            {
                "items": [user],
                "total": 1,
                "page": 1,
                "page_size": 25,
                "total_pages": 1,
                "has_next": False,
                "has_prev": False,
            },
            {user.id: employee},
        )
    )

    result = await service.list_accounts(
        actor,
        page=1,
        page_size=25,
        search="demo.engineer",
        sort_by=None,
        sort_order="asc",
    )

    assert result.total == 1
    assert result.items[0].username == "demo.engineer"
    assert result.items[0].employee_code == "EMP-012"


@pytest.mark.asyncio
async def test_password_support_is_super_admin_only():
    service = service_with_mocks()
    actor = SimpleNamespace(is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        await service.reset_password(actor, 20, "password")

    assert exc.value.status_code == 403
    service.repo.get_workforce_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_super_admin_temporary_password_reset_is_audited_and_revokes_sessions(monkeypatch):
    service = service_with_mocks()
    actor = SimpleNamespace(is_superuser=True, hashed_password="admin-hash")
    target = SimpleNamespace(
        hashed_password="old-hash",
        must_change_password=False,
        password_recovery_token_hash="recovery-hash",
        password_recovery_expires_at=object(),
    )
    service.repo.get_workforce_user.return_value = target
    service._temporary_password = AsyncMock(return_value="Random!Temporary9284")
    auth_service = SimpleNamespace(revoke_all=AsyncMock(return_value=2))
    monkeypatch.setattr(module, "AuthService", lambda session: auth_service)

    password, revoked = await service.reset_password(actor, 20, "admin-password")

    assert password == "Random!Temporary9284"
    assert revoked == 2
    assert target.hashed_password == "new-password-hash"
    assert target.must_change_password is True
    assert target.password_recovery_token_hash is None
    assert target.password_recovery_expires_at is None
    auth_service.revoke_all.assert_awaited_once_with(
        target,
        actor=actor,
        reason="password_reset:super_admin",
        action=AuditAction.PASSWORD_RESET,
        ip_address=None,
        request_id=None,
    )


@pytest.mark.asyncio
async def test_super_admin_mfa_reset_clears_factor_and_revokes_sessions(monkeypatch):
    service = service_with_mocks()
    actor = SimpleNamespace(is_superuser=True, hashed_password="admin-hash")
    target = SimpleNamespace(
        mfa_enabled=True,
        mfa_secret="encrypted-secret",
        mfa_pending_secret="pending-secret",
        mfa_pending_expires_at=object(),
        mfa_enrolled_at=object(),
        mfa_last_used_step=123,
        mfa_recovery_code_hashes="[]",
        last_mfa_verified_at=object(),
    )
    service.repo.get_workforce_user.return_value = target
    auth_service = SimpleNamespace(revoke_all=AsyncMock(return_value=1))
    monkeypatch.setattr(module, "AuthService", lambda session: auth_service)

    revoked = await service.reset_mfa(actor, 20, "admin-password")

    assert revoked == 1
    assert target.mfa_enabled is False
    assert target.mfa_secret is None
    assert target.mfa_pending_secret is None
    assert target.mfa_recovery_code_hashes is None
    assert target.last_mfa_verified_at is None
    auth_service.revoke_all.assert_awaited_once_with(
        target,
        actor=actor,
        reason="mfa_reset:super_admin",
        action=AuditAction.MFA_ADMIN_RESET,
        ip_address=None,
        request_id=None,
    )
