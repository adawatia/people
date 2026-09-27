"""
core/auth.py — Authentication wiring, password policy and permission helpers.

Built on fastapi-users. Login accepts username or Indian mobile
number; passwords are enforced by ``core.password_policy``; API access is
authorized through an effective permission set — the implicit
``BASE_EMPLOYEE_PERMISSIONS`` every employee holds plus the bundle of an
optional elevated business role (see this module's bottom section) — or the
ERP API key. Row scope resolution lives in ``core.employee_access`` and the
session lifecycle (rotation, revocation, idle/absolute expiry) lives in
``services/auth_service.py``.
"""

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.authentication import AuthenticationBackend
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import InvalidPasswordException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.business_roles import (
    ELEVATED_BUSINESS_ROLES,
    EMPLOYEE,
    resolve_business_role,
)
from core.database import check_database_connection as _check_database_connection
from core.database import get_async_session
from core.mobile import normalize_indian_mobile
from core.password_policy import PasswordCheckContext, PasswordPolicyError, validate_password_policy
from core.settings import get_settings
from core.tokens import ACCESS_TOKEN_AUDIENCE, decode_token
from db.models import AuthSession, Employee, User, now_ist
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

        The rules themselves live in ``core.password_policy`` so they can be
        unit-tested without a user row and reviewed in one place: length rules,
        composition, personal-information rejection, zxcvbn strength scoring and
        a breached/common-password check.  This method only adapts the outcome to
        fastapi-users' exception.
        """
        context = PasswordCheckContext(
            email=getattr(user, "email", None),
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
        )
        try:
            await validate_password_policy(password, context=context)
        except PasswordPolicyError as exc:
            raise InvalidPasswordException(reason=exc.reason) from exc

        await super().validate_password(password, user)

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        return None

    async def authenticate(self, credentials):
        """Override to support login by mobile_number OR username.

        fastapi-users sends the form `username` field. We treat it as:
          mobile / username — lookup
        """

        login_value: str = credentials.username.strip()

        # Resolve the user by mobile or username. Email is not a login identity.
        user: User | None = None
        from sqlalchemy import select as sa_select

        from core.database import get_async_session as _get_session

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


from fastapi_users.authentication import BearerTransport

# Swagger's OAuth2 Authorize dialog needs one concrete password-flow URL.
# Employee login is the regular application flow; Super Admin uses its
# dedicated endpoint directly because OAuth2 supports only one tokenUrl here.
bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/employee/login")


def get_jwt_strategy() -> object:
    """Build the JWT strategy used to *validate* bearer tokens.

    Historically this minted an 8-hour login token that clients exchanged for a
    session, which left an independently-valid credential alive for a workday.
    Login now issues the short-lived session access token directly (see
    ``services/auth_service.py``), so this strategy only needs to describe the
    same token shape and a short lifetime for any remaining minting callers
    (Swagger's OAuth2 password flow, tests).
    """
    from fastapi_users.authentication.strategy.jwt import JWTStrategy

    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=settings.login_exchange_token_ttl_seconds)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, int](get_user_manager, [auth_backend])
current_active_user = fastapi_users.current_user(active=True)


async def current_sensitive_user(
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Require the access token's server-side session to remain live.

    Ordinary business reads accept the short JWT revocation window. Account and
    security operations use this dependency so a revoked privileged session
    cannot continue changing credentials until token expiry.
    """
    import jwt

    header = request.headers.get("authorization", "")
    scheme, _, raw_token = header.partition(" ")
    try:
        payload = decode_token(raw_token, secret=settings.jwt_secret, audience=ACCESS_TOKEN_AUDIENCE)
        session_id = int(payload["sid"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer active") from exc
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer active")
    auth_session = await session.get(AuthSession, session_id)
    now = now_ist()
    if (
        auth_session is None
        or auth_session.user_id != user.id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
        or auth_session.absolute_expires_at <= now
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer active")
    request.state.auth_session = auth_session
    return user


async def user_has_permission(user: User, permission_code: str, session: AsyncSession) -> bool:
    """Convenience check: does this user hold the given permission?"""
    permissions = await get_user_permissions(user, session)
    return permission_code in permissions


def effective_permissions(business_role: str | None) -> set[str]:
    """Effective permission set for a business role (``None`` = plain employee).

    Every employee holds the base self-service set; an elevated business role
    adds its own bundle on top.  The elevated bundles therefore list only the
    permissions they *add* — base permissions are never duplicated into them.
    """
    permissions = set(BASE_EMPLOYEE_PERMISSIONS)
    if business_role:
        permissions |= ROLE_PERMISSIONS.get(business_role, set())
    return permissions


async def get_user_permissions(user: User, session: AsyncSession) -> list[str]:
    """Resolve the effective permission set for a user.

    Permissions are the base employee set plus the bundle of the linked
    employee's elevated business role, if any. Technical administrators and
    unlinked accounts are deliberately denied business permissions.
    """
    if user.is_superuser:
        return sorted(TECHNICAL_ADMIN_PERMISSIONS)

    employee = await session.scalar(select(Employee).where(Employee.user_id == user.id))
    if employee is None:
        return []
    business_role = resolve_business_role(employee)
    return sorted(effective_permissions(business_role))


PASSWORD_CHANGE_REQUIRED = {
    "code": "PASSWORD_CHANGE_REQUIRED",
    "message": "Change the temporary password before using People HRMS.",
}
TECHNICAL_ADMIN_ONLY = {
    "code": "TECHNICAL_ADMIN_ONLY",
    "message": "Technical administrator accounts cannot access workforce operations.",
}
WORKFORCE_ACCOUNT_REQUIRED = {
    "code": "WORKFORCE_ACCOUNT_REQUIRED",
    "message": "This login account is not linked to an employee record.",
}


async def current_business_user(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Require an active, fully initialized workforce account.

    Temporary-password sessions are intentionally restricted to account
    bootstrap routes, and the technical Super Admin is kept outside the ERP
    and business-role boundary even if a caller bypasses the Nuxt navigation.
    """
    if user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PASSWORD_CHANGE_REQUIRED)
    if user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=TECHNICAL_ADMIN_ONLY)
    employee_id = await session.scalar(select(Employee.id).where(Employee.user_id == user.id))
    if employee_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=WORKFORCE_ACCOUNT_REQUIRED)
    return user


def require_permission(permission_code: str):
    """FastAPI dependency factory: allow the route only with this permission."""

    async def dependency(
        current_user: User = Depends(current_business_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> User:
        if not await user_has_permission(current_user, permission_code, session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "You do not have access to this operation."},
            )
        return current_user

    return dependency


# The single source of truth for what a user may do.
#
# BASE_EMPLOYEE_PERMISSIONS is implicit: every employee holds it.  Elevated
# bundles intentionally list only the permissions the role *adds*, so no code
# is duplicated between roles.  The role/scope columns themselves live on
# Employee and are provisioned by ERP; the web UI reads the resolved list from
# /users/me rather than hard-coding any of this.
BASE_EMPLOYEE_PERMISSIONS: set[str] = {
    "employee.view_self",
    "attendance.view_self",
    "leave.apply",
    "leave.view_self",
    "leave.cancel",
    "work_arrangement.apply",
    "work_arrangement.view_self",
    "work_arrangement.cancel",
    "shift.view_self",
    "overtime.view_self",
}

TECHNICAL_ADMIN_PERMISSIONS: set[str] = {
    "technical.account.view",
    "technical.account.manage",
    "technical.system.view",
    "technical.system.configure",
    "technical.audit.view",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "DEPARTMENT_MANAGER": {
        "employee.view",
        "attendance.view_department",
        "leave.approve",
        "leave.reject",
        "work_arrangement.approve",
        "work_arrangement.reject",
        "overtime.view_department",
        "overtime.approve",
        "reports.attendance",
        "reports.leave",
    },
    "HR_ADMIN": {
        "user.view",
        "user.create",
        "user.update",
        "user.deactivate",
        "employee.view",
        "employee.create",
        "employee.update",
        "employee.deactivate",
        "designation.view",
        "designation.create",
        "designation.update",
        "designation.delete",
        "attendance.view",
        "attendance.view_unit",
        "attendance.view_department",
        "attendance.process",
        "attendance.correct",
        "leave.manage",
        "leave.approve",
        "leave.reject",
        "work_arrangement.manage",
        "work_arrangement.approve",
        "work_arrangement.reject",
        "shift.assign",
        "shift.update",
        "overtime.approve",
        "overtime.view_department",
        "reports.view",
        "reports.attendance",
        "reports.leave",
        "reports.overtime",
        "reports.salary_cost",
        "system.configure",
        "audit.view",
        "salary_cost.view_unit",
        "salary_cost.view_department",
    },
    "ORGANIZATION_OWNER": {
        "employee.view",
        "attendance.view",
        "attendance.view_unit",
        "attendance.view_department",
        "overtime.view",
        "overtime.view_department",
        "reports.view",
        "reports.attendance",
        "reports.leave",
        "reports.overtime",
        "dashboard.view_organization",
    },
}

# The keys are string literals (not the role constants) so the permission
# catalogue tests can read them statically; this keeps them honest.
assert set(ROLE_PERMISSIONS) == set(ELEVATED_BUSINESS_ROLES)

# Backward-compatible role → full permission-set view (base + role bundle).
# Kept because it names the four persisted role values and is asserted by the
# permission-catalog tests; runtime code resolves through
# ``effective_permissions`` so base permissions stay unduplicated.
FIXED_ROLE_PERMISSIONS: dict[str, set[str]] = {
    role: effective_permissions(role) for role in (EMPLOYEE, *ELEVATED_BUSINESS_ROLES)
}


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
    storage_uri=settings.redis_url if settings.auth_throttle_backend == "redis" else "memory://",
)


def setup_rate_limits(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


def check_database_connection() -> None:
    _check_database_connection()
