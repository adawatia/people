import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from core.database import async_session_maker
from core.invitation import (
    create_invitation_for_user,
    find_user_by_invitation_token,
    hash_token,
)
from db.models import User, now_ist


@pytest.fixture
def run_async_helper():
    import selectors
    import sys
    def _run(coro):
        if sys.platform == "win32":
            return asyncio.run(coro, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
        return asyncio.run(coro)
    return _run


def test_invitation_token_creation_and_hashing():
    user = User(
        email="invite-test@example.com",
        username="invitetest",
        is_active=False,
        is_verified=False,
    )
    raw_token = create_invitation_for_user(user)

    assert raw_token is not None
    assert len(raw_token) > 20
    assert user.invitation_token_hash == hash_token(raw_token)
    assert user.invitation_sent_at is not None
    assert user.invitation_expires_at is not None
    assert user.invitation_used_at is None


def test_invitation_token_validation(run_async_helper):
    async def _test():
        from db.seed import create_db_and_tables
        await create_db_and_tables()

        async with async_session_maker() as session:
            # Clean up potential leftover
            existing = await session.scalar(select(User).where(User.email == "token-val@example.com"))
            if existing:
                await session.delete(existing)
                await session.commit()

            # Create user
            user = User(
                email="token-val@example.com",
                username="tokenval",
                hashed_password="some-hashed-password",
                is_active=False,
                is_verified=False,
            )
            raw_token = create_invitation_for_user(user)
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # 1. Valid token lookup
            found_user, error = await find_user_by_invitation_token(session, raw_token)
            assert found_user is not None
            assert found_user.id == user.id
            assert error is None

            # 2. Invalid token lookup
            invalid_user, error = await find_user_by_invitation_token(session, "completely-wrong-token-1234567890")
            assert invalid_user is None
            assert "invalid or has already been replaced" in error

            # 3. Consumed / used token
            user.invitation_used_at = now_ist()
            await session.commit()
            used_user, error = await find_user_by_invitation_token(session, raw_token)
            assert used_user is None
            assert "already been used" in error

            # 4. Expired token
            user.invitation_used_at = None
            user.invitation_expires_at = now_ist() - timedelta(hours=1)
            await session.commit()
            expired_user, error = await find_user_by_invitation_token(session, raw_token)
            assert expired_user is None
            assert "expired" in error

            # Clean up
            await session.delete(user)
            await session.commit()

    run_async_helper(_test())


def test_validate_password_none_check(run_async_helper):
    async def _test():
        from core.auth import UserManager, get_user_db
        from core.database import async_session_maker
        from fastapi_users.exceptions import InvalidPasswordException

        async with async_session_maker() as session:
            user_db = [udb async for udb in get_user_db(session)][0]
            user_mgr = UserManager(user_db)

            # Test that passing None raises InvalidPasswordException without TypeError
            with pytest.raises(InvalidPasswordException) as exc_info:
                await user_mgr.validate_password(None, None)
            assert "Password is required" in str(exc_info.value.reason)

    run_async_helper(_test())

