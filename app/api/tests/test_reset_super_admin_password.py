from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import reset_super_admin_password as reset_utility


@pytest.mark.asyncio
async def test_offline_super_admin_reset_applies_all_security_effects(monkeypatch):
    user = SimpleNamespace(
        hashed_password="old-hash",
        must_change_password=True,
        password_recovery_token_hash="active-token-hash",
        password_recovery_expires_at=object(),
    )
    manager = SimpleNamespace(password_helper=SimpleNamespace(hash=Mock(return_value="new-argon2-hash")))
    auth_service = SimpleNamespace(revoke_all=AsyncMock(return_value=3))
    monkeypatch.setattr(reset_utility, "AuthService", lambda session: auth_service)

    revoked = await reset_utility.apply_reset(object(), user, manager, "Strong!Passphrase928")

    assert revoked == 3
    assert user.hashed_password == "new-argon2-hash"
    assert user.must_change_password is False
    assert user.password_recovery_token_hash is None
    assert user.password_recovery_expires_at is None
    auth_service.revoke_all.assert_awaited_once_with(
        user,
        reason="password_reset:offline_recovery",
        action=reset_utility.AuditAction.PASSWORD_RESET,
    )
