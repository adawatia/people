"""
core/auth.py — Authentication, password policy and permission helpers.

Built on fastapi-users. Login accepts email, username, or Indian mobile
number; passwords are enforced by a strict local policy; API access is
authorized through fixed role-based permission sets (see
FIXED_ROLE_PERMISSIONS at the bottom of this file) or the ERP API key.
"""

import asyncio
import secrets
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
from core.mobile import normalize_indian_mobile
from db.models import Employee, User
from schemas import UserCreate

settings = get_settings()


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> SQLAlchemyUserDatabase[User, int]:
    """fastapi-users hook: expose the User table as its user database."""
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """Core user operations: validation, authentication and lifecycle hooks."""

    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def validate_password(self, password: str, user: User | UserCreate) -> None:
        """Enforce the password policy; called on register and password change.

        Layers, in order:
        1. Hard rules — minimum length and character-class requirements.
        2. Personal-info check — reject passwords containing the user's own
           email, username, or name fragments.
        3. Strength scoring — zxcvbn (real-world crack estimation) must rate
           the password at least 3/4, considering the personal info above.
        """
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
                normalized_mobile = None
                try:
                    normalized_mobile = normalize_indian_mobile(login_value)
                except ValueError:
                    pass
                filters = [User.username == login_value]
                if normalized_mobile:
                    filters.append(User.mobile_number == normalized_mobile)
                stmt = sa_select(User).where(or_(*filters))
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                break

        if user is None:
            # Run dummy hash to mitigate timing attacks (matching BaseUserManager pattern):
            # hashing even for unknown users keeps response times uniform, so an
            # attacker cannot infer whether an account exists from latency.
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
            # Opportunistic hash upgrade: if the hashing scheme parameters have
            # changed since this password was stored, persist the new hash.
            user.hashed_password = updated_hash
            try:
                await self.user_db.update(user, {"hashed_password": updated_hash})
            except Exception:
                pass
        return user

    async def on_after_request_verify(self, user: User, token: str, request: Request | None = None) -> None:
        return None

    async def update(
        self,
        user_update,
        user: User,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        """Intercept profile updates to handle email-change security."""
        original_email = user.email

        # Prevent manual 'is_verified=True' from overriding the unverify logic when email changes
        if getattr(user_update, "email", None) and str(user_update.email) != str(original_email):
            if hasattr(user_update, "is_verified"):
                user_update.is_verified = False

        updated_user = await super().update(user_update, user, safe, request)

        if original_email != updated_user.email:
            # The email actually changed: force re-verification so a stale
            # verified flag cannot be carried over to the new address.
            updated_user.is_verified = False

        return updated_user

    async def on_after_forgot_password(self, user: User, token: str, request: Request | None = None) -> None:
        return None

    async def on_after_reset_password(self, user: User, request: Request | None = None) -> None:
        return None


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, int] = Depends(get_user_db),
) -> UserManager:
    """fastapi-users hook: provide the request-scoped UserManager."""
    yield UserManager(user_db)


from fastapi_users.authentication import AuthenticationBackend, BearerTransport

# Swagger's OAuth2 Authorize dialog needs one concrete password-flow URL.
# Employee login is the regular application flow; Super Admin uses its
# dedicated endpoint directly because OAuth2 supports only one tokenUrl here.
bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/employee/login")

def get_jwt_strategy() -> object:
    """Build the JWT strategy — access tokens live 8 hours per workday."""
    from fastapi_users.authentication.strategy.jwt import JWTStrategy

    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=28800)  # 8 hours


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, int](get_user_manager, [auth_backend])
current_active_user = fastapi_users.current_user(active=True)


async def user_has_permission(user: User, permission_code: str, session: AsyncSession) -> bool:
    """Convenience check: does this user hold the given permission?"""
    permissions = await get_user_permissions(user, session)
    return permission_code in permissions


async def get_user_permissions(user: User, session: AsyncSession) -> list[str]:
    """Resolve the effective permission set for a user.

    Permissions are derived from the fixed role on the linked Employee
    record; Super Admins always receive the full HR_ADMIN set. Users
    without an employee profile fall back to the plain EMPLOYEE set.
    """
    if user.is_superuser:
        return sorted(FIXED_ROLE_PERMISSIONS["HR_ADMIN"])

    employee = await session.scalar(select(Employee).where(Employee.user_id == user.id))
    role = employee.role if employee and employee.role in FIXED_ROLE_PERMISSIONS else "EMPLOYEE"
    return sorted(FIXED_ROLE_PERMISSIONS[role])


def require_permission(permission_code: str):
    """FastAPI dependency factory: allow the route only with this permission."""
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


# The single source of truth for what each business role can do.
# Roles live on Employee.role and are provisioned by ERP; the web UI also
# queries this mapping indirectly via /auth/account permissions.
FIXED_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "EMPLOYEE": {
        "employee.view_self", "attendance.view_self", "leave.apply", "leave.view_self",
        "leave.cancel", "work_arrangement.apply", "work_arrangement.view_self",
        "work_arrangement.cancel", "shift.view_self", "overtime.view_self",
    },
    "DEPARTMENT_MANAGER": {
        "employee.view", "employee.view_self", "attendance.view_department", "attendance.view_self",
        "leave.approve", "leave.reject", "leave.apply", "leave.view_self", "leave.cancel",
        "work_arrangement.approve", "work_arrangement.reject", "work_arrangement.apply",
        "work_arrangement.view_self", "work_arrangement.cancel", "overtime.view_department",
        "overtime.approve", "reports.attendance", "reports.leave", "shift.view_self",
        "overtime.view_self",
    },
    "HR_ADMIN": {
        "user.view", "user.create", "user.update", "user.deactivate", "employee.view", "employee.create",
        "employee.update", "employee.deactivate", "designation.view", "designation.create",
        "designation.update", "designation.delete", "attendance.view", "attendance.view_unit",
        "attendance.view_department", "attendance.process", "attendance.correct", "leave.manage",
        "leave.approve", "leave.reject", "leave.cancel", "work_arrangement.manage",
        "work_arrangement.approve", "work_arrangement.reject", "work_arrangement.cancel",
        "shift.assign", "shift.update", "overtime.approve", "overtime.view_department",
        "reports.view", "reports.attendance", "reports.leave", "reports.overtime", "reports.salary_cost",
        "system.configure", "audit.view", "salary_cost.view_unit", "salary_cost.view_department",
    },
}


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


# ── ERP machine-to-machine authentication ────────────────────────────────────

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="ERP integration key. Configure ERP_API_KEY on the API server; never expose this key in the browser.",
)


async def verify_api_key(api_key_header: str = Security(api_key_header)):
    """Validate the ERP integration key sent in the X-API-Key header.

    compare_digest runs in constant time so key length/content cannot be
    probed via timing differences.
    """
    expected = settings.erp_api_key or settings.api_key
    if api_key_header and secrets.compare_digest(api_key_header, expected):
        return True
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate API KEY")


verify_erp_api_key = verify_api_key
