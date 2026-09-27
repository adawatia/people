"""Interactively recover a Super Admin password from the API host.

Run this from ``app/api`` so ``core.settings`` loads the same ``.env`` and
PostgreSQL database as the application::

    uv run python reset_super_admin_password.py
    uv run python reset_super_admin_password.py --identity superadmin

The utility deliberately never accepts a password as a command-line argument,
where it could be retained in shell history or exposed in the process list.
"""

import argparse
import asyncio
import getpass
import selectors
import sys

from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import InvalidPasswordException
from sqlalchemy import func, or_, select

from core.auth import UserManager
from core.database import async_session_maker
from core.settings import get_settings
from db.models import User
from services.auth_service import AuditAction, AuthService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset a Super Admin password, revoke its sessions, and invalidate password-recovery tokens."
    )
    parser.add_argument(
        "--identity",
        help="Super Admin username or email used to locate the account. The password is always prompted securely.",
    )
    return parser.parse_args()


def read_identity(configured_username: str, supplied_identity: str | None) -> str:
    if supplied_identity is not None:
        identity = supplied_identity.strip()
    else:
        identity = input(f"Super Admin username or email [{configured_username}]: ").strip() or configured_username
    if not identity:
        raise ValueError("The account identity cannot be empty.")
    return identity


async def find_super_admin(session, identity: str) -> User:
    """Find one Super Admin under a row lock and reject ambiguous identities."""
    normalized = identity.casefold()
    statement = (
        select(User)
        .where(
            or_(func.lower(User.email) == normalized, func.lower(User.username) == normalized),
            User.is_superuser.is_(True),
        )
        .with_for_update()
    )
    matches = list((await session.scalars(statement)).all())
    if not matches:
        raise LookupError(f"No Super Admin account matches {identity!r}.")
    if len(matches) > 1:
        raise LookupError(
            "That value matches more than one Super Admin account across username and email; use an unambiguous value."
        )
    return matches[0]


async def prompt_for_valid_password(manager: UserManager, user: User) -> str:
    settings = get_settings()
    while True:
        password = getpass.getpass("New password: ")
        confirmation = getpass.getpass("Confirm new password: ")
        if password != confirmation:
            print("Passwords do not match. Please try again.", file=sys.stderr)
            continue
        try:
            await manager.validate_password(password, user)
        except InvalidPasswordException as exc:
            print(f"Invalid password: {exc.reason}", file=sys.stderr)
            print(
                f"Use a strong {settings.password_min_length}-{settings.password_max_length} character passphrase; "
                "avoid personal information and breached or common values.",
                file=sys.stderr,
            )
            continue
        return password


async def apply_reset(session, user: User, manager: UserManager, password: str) -> int:
    """Apply all password-reset security effects in one committed transaction."""
    user.hashed_password = manager.password_helper.hash(password)
    user.must_change_password = False
    user.password_recovery_token_hash = None
    user.password_recovery_expires_at = None
    return await AuthService(session).revoke_all(
        user,
        reason="password_reset:offline_recovery",
        action=AuditAction.PASSWORD_RESET,
    )


async def reset_super_admin_password(identity: str | None = None) -> bool:
    settings = get_settings()
    try:
        resolved_identity = read_identity(settings.super_admin_username, identity)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return False

    async with async_session_maker() as session:
        try:
            user = await find_super_admin(session, resolved_identity)
            print(f"Found Super Admin: {user.username} ({user.email})")
            manager = UserManager(SQLAlchemyUserDatabase(session, User))
            password = await prompt_for_valid_password(manager, user)
            revoked = await apply_reset(session, user, manager, password)
        except (EOFError, KeyboardInterrupt):
            await session.rollback()
            print("\nCancelled.")
            return False
        except LookupError as exc:
            await session.rollback()
            print(f"Error: {exc}", file=sys.stderr)
            return False
        except Exception as exc:
            await session.rollback()
            print(f"Password reset failed: {exc}", file=sys.stderr)
            return False

    print("Password reset successfully.")
    print(f"Revoked refresh sessions: {revoked}")
    print("Outstanding password-recovery tokens were invalidated. MFA enrollment was preserved.")
    print("Previously issued access tokens can remain valid until their short expiry; sign in with the new password.")
    return True


def main() -> int:
    args = parse_args()
    print("=== Super Admin Password Recovery ===")
    coroutine = reset_super_admin_password(args.identity)
    if sys.platform == "win32":
        succeeded = asyncio.run(coroutine, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    else:
        succeeded = asyncio.run(coroutine)
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
