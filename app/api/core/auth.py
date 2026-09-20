import asyncio
import re
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends, FastAPI, Request, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import InvalidPasswordException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import or_, select
from zxcvbn import zxcvbn

from core.database import check_database_connection as _check_database_connection
from core.database import get_async_session
from core.settings import get_settings
from db.models import Permission, RolePermission, User, UserRoleAssignment
from schemas import UserCreate

settings = get_settings()


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> SQLAlchemyUserDatabase[User, int]:
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def validate_password(self, password: str, user: User | UserCreate) -> None:
        if not password:
            raise InvalidPasswordException(reason="Password is required")

        if len(password) < 12:
            raise InvalidPasswordException(reason="Password must be at least 12 characters long")

        if not re.search(r"[A-Z]", password):
            raise InvalidPasswordException(reason="Password must contain at least one uppercase letter")

        if not re.search(r"[a-z]", password):
            raise InvalidPasswordException(reason="Password must contain at least one lowercase letter")

        if not re.search(r"\d", password):
            raise InvalidPasswordException(reason="Password must contain at least one number")

        if not re.search(r"[^A-Za-z0-9]", password):
            raise InvalidPasswordException(reason="Password must contain at least one special character")

        forbidden_parts = []
        if getattr(user, "email", None):
            forbidden_parts.append(str(user.email).split("@")[0].lower())
        if getattr(user, "username", None):
            forbidden_parts.append(str(user.username).lower())
        if getattr(user, "first_name", None):
            forbidden_parts.append(str(user.first_name).lower())
        if getattr(user, "last_name", None):
            forbidden_parts.append(str(user.last_name).lower())

        password_lower = password.lower()
        for part in forbidden_parts:
            if part and len(part) >= 3 and part in password_lower:
                raise InvalidPasswordException(reason="Password must not contain user email, name, or username")

        results = zxcvbn(password, user_inputs=forbidden_parts)
        if results.get("score", 0) < 3:
            reason = results.get("feedback", {}).get("warning") or "Password is too weak"
            raise InvalidPasswordException(reason=reason)

        await super().validate_password(password, user)

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        return None

    async def authenticate(self, credentials):
        """Override to support login by email OR mobile_number OR username.

        fastapi-users sends the form `username` field. We treat it as:
          1. email  — if it contains '@'
          2. mobile / username — lookup
        """
        from fastapi_users.exceptions import UserNotExists

        login_value: str = credentials.username.strip()

        # Resolve the user by email, mobile, or username
        user: User | None = None
        if "@" in login_value:
            try:
                user = await self.get_by_email(login_value)
            except UserNotExists:
                user = None

        if user is None:
            # Try username or mobile_number lookup
            from sqlalchemy import select as sa_select
            from core.database import get_async_session as _get_session  # noqa: PLC0415

            async for session in _get_session():
                stmt = sa_select(User).where((User.username == login_value) | (User.mobile_number == login_value))
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                break

        if user is None:
            # Run dummy hash to mitigate timing attacks (matching BaseUserManager pattern)
            try:
                self.password_helper.hash(credentials.password)
            except Exception:
                pass
            return None

        try:
            verified, updated_hash = self.password_helper.verify_and_update(credentials.password, user.hashed_password)
        except Exception:
            return None

        if not verified:
            return None
        if updated_hash is not None:
            user.hashed_password = updated_hash
            try:
                await self.user_db.update(user, {"hashed_password": updated_hash})
            except Exception:
                pass
        return user

    async def on_after_request_verify(self, user: User, token: str, request: Request | None = None) -> None:
        from core.email import get_email_service

        email_svc = get_email_service()

        frontend_url = settings.frontend_url.rstrip("/")
        verify_url = f"{frontend_url}/verify-email?token={token}"
        user_name = user.first_name or user.username or "User"

        asyncio.create_task(
            email_svc.send_verification_email(
                to_email=user.email,
                user_name=user_name,
                verify_url=verify_url,
            )
        )

    async def update(
        self,
        user_update,
        user: User,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        original_email = user.email

        # Prevent manual 'is_verified=True' from overriding the unverify logic when email changes
        if getattr(user_update, "email", None) and str(user_update.email) != str(original_email):
            if hasattr(user_update, "is_verified"):
                user_update.is_verified = False

        updated_user = await super().update(user_update, user, safe, request)

        if original_email != updated_user.email:
            # Email has actually changed

            # 1. Send Security Alert to Old Email
            from core.email import get_email_service

            email_svc = get_email_service()
            asyncio.create_task(
                email_svc.send_email_changed_alert(
                    old_email=original_email,
                    new_email=updated_user.email,
                )
            )

            # 2. Trigger Verification Email to New Email
            from fastapi_users.exceptions import UserAlreadyVerified

            try:
                await self.request_verify(updated_user, request)
            except UserAlreadyVerified:
                # Fallback if somehow it's marked verified (e.g. superadmin bypass)
                pass

        return updated_user

    async def on_after_forgot_password(self, user: User, token: str, request: Request | None = None) -> None:
        from core.email import get_email_service

        email_svc = get_email_service()

        frontend_url = settings.frontend_url.rstrip("/")
        reset_url = f"{frontend_url}/reset-password?token={token}"
        user_name = user.first_name or user.username or "User"

        asyncio.create_task(
            email_svc.send_password_reset_email(
                to_email=user.email,
                user_name=user_name,
                username=user.username or user.email,
                reset_url=reset_url,
            )
        )

    async def on_after_reset_password(self, user: User, request: Request | None = None) -> None:
        return None


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, int] = Depends(get_user_db),
) -> UserManager:
    yield UserManager(user_db)


from fastapi_users.authentication import AuthenticationBackend, BearerTransport, CookieTransport

bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/jwt/login")

cookie_transport = CookieTransport(
    cookie_name="hrms_auth",
    cookie_max_age=28800,  # 8 hours — suitable for a full work day
    cookie_secure=False,  # Set to True in production
    cookie_httponly=True,
    cookie_samesite="lax",
)


def get_jwt_strategy() -> object:
    from fastapi_users.authentication.strategy.jwt import JWTStrategy

    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=28800)  # 8 hours


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

cookie_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, int](get_user_manager, [auth_backend, cookie_backend])
current_active_user = fastapi_users.current_user(active=True)


async def user_has_permission(user: User, permission_code: str, session: AsyncSession) -> bool:
    if user.is_superuser:
        return True

    # Read exclusively from UserRoleAssignment (no legacy UserRole)
    user_role_ids = select(UserRoleAssignment.role_id).where(UserRoleAssignment.user_id == user.id)
    query = (
        select(Permission.permission_id)
        .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
        .where(
            RolePermission.role_id.in_(user_role_ids),
            Permission.permission_code == permission_code,
        )
        .limit(1)
    )
    return await session.scalar(query) is not None


async def get_user_permissions(user: User, session: AsyncSession) -> list[str]:
    if user.is_superuser:
        all_perms = await session.execute(select(Permission.permission_code))
        return sorted(all_perms.scalars().all())

    # Read exclusively from UserRoleAssignment
    user_role_ids = select(UserRoleAssignment.role_id).where(UserRoleAssignment.user_id == user.id)
    query = (
        select(Permission.permission_code)
        .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
        .where(RolePermission.role_id.in_(user_role_ids))
        .distinct()
    )
    perms = (await session.execute(query)).scalars().all()
    return sorted(perms)


def require_permission(permission_code: str):
    async def dependency(
        current_user: User = Depends(fastapi_users.current_user(active=True)),
        session: AsyncSession = Depends(get_async_session),
    ) -> User:
        if not await user_has_permission(current_user, permission_code, session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_code}",
            )
        return current_user

    return dependency


limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"], storage_uri="memory://")


def setup_rate_limits(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def ensure_permission(email: str, path: str, method: str) -> bool:
    if path in {"/admin"}:
        return bool(email)

    return bool(email)


def check_database_connection() -> None:
    _check_database_connection()


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == settings.api_key:
        return True
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate API KEY")
