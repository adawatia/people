"""
core/rbac.py — Dynamic RBAC helpers.

Design principles:
- Role = generic job function (e.g. "Unit Head")
- Scope = where that role applies (organization | unit | department + scope_id)
- Users can hold multiple role assignments simultaneously.
- Super Admin / Admin can *assign* existing roles; only Super Admin can *define* roles.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_async_session
from db.models import Permission, Role, RolePermission, User, UserRoleAssignment

ScopeLevel = Literal["department", "unit", "organization"]

# Scope precedence: higher index = higher access
_SCOPE_ORDER: list[ScopeLevel] = ["department", "unit", "organization"]


def scope_level(scope: ScopeLevel | None) -> int:
    """Return numeric level for scope comparison (higher = broader access)."""
    if scope is None:
        return -1
    try:
        return _SCOPE_ORDER.index(scope)
    except ValueError:
        return -1


def scope_satisfies(user_max_scope: ScopeLevel | None, required_min_scope: ScopeLevel) -> bool:
    """True if the user's broadest scope is at least `required_min_scope`."""
    return scope_level(user_max_scope) >= scope_level(required_min_scope)


async def get_user_role_assignments(
    user_id: int, session: AsyncSession
) -> list[UserRoleAssignment]:
    """Load all role assignments for a user, with role and permissions eager-loaded."""
    result = await session.execute(
        select(UserRoleAssignment)
        .options(
            selectinload(UserRoleAssignment.role).selectinload(Role.permission_links).selectinload(RolePermission.permission)
        )
        .where(UserRoleAssignment.user_id == user_id)
    )
    return list(result.scalars().all())


async def get_effective_permissions(user_id: int, session: AsyncSession) -> set[str]:
    """Return the union of all permission codes across all of a user's role assignments."""
    assignments = await get_user_role_assignments(user_id, session)
    permissions: set[str] = set()
    for assignment in assignments:
        if assignment.role:
            for link in assignment.role.permission_links:
                if link.permission:
                    permissions.add(link.permission.permission_code)
    return permissions


async def get_max_scope_level(user_id: int, session: AsyncSession) -> ScopeLevel | None:
    """Return the broadest scope level the user holds (organization > unit > department)."""
    assignments = await get_user_role_assignments(user_id, session)
    if not assignments:
        return None
    max_level = -1
    max_scope: ScopeLevel | None = None
    for assignment in assignments:
        lvl = scope_level(assignment.scope_type)  # type: ignore[arg-type]
        if lvl > max_level:
            max_level = lvl
            max_scope = assignment.scope_type  # type: ignore[assignment]
    return max_scope


async def has_permission(
    user: User,
    permission_code: str,
    session: AsyncSession,
    *,
    scope_type: ScopeLevel | None = None,
    scope_id: int | None = None,
) -> bool:
    """
    Return True if the user holds `permission_code` in *any* of their role assignments,
    optionally narrowed by a specific scope_type and scope_id.

    Super Admin (is_superuser=True) always returns True.
    """
    if user.is_superuser:
        return True

    assignments = await get_user_role_assignments(user.id, session)
    for assignment in assignments:
        # Scope check: if caller specifies a required scope, must match or be broader
        if scope_type is not None:
            if scope_level(assignment.scope_type) < scope_level(scope_type):  # type: ignore[arg-type]
                continue
            if scope_id is not None and assignment.scope_id is not None and assignment.scope_id != scope_id:
                continue

        if assignment.role:
            for link in assignment.role.permission_links:
                if link.permission and link.permission.permission_code == permission_code:
                    return True
    return False


async def require_rbac_permission(
    permission_code: str,
    session: AsyncSession,
    user: User,
) -> User:
    """FastAPI-compatible guard that raises 403 if permission missing."""
    if not await has_permission(user, permission_code, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {permission_code}",
        )
    return user


def require_permission_dep(permission_code: str):
    """Returns a FastAPI dependency that enforces a single permission."""
    from core.auth import fastapi_users  # local import to avoid circular

    async def _dep(
        user: User = Depends(fastapi_users.current_user(active=True)),
        session: AsyncSession = Depends(get_async_session),
    ) -> User:
        return await require_rbac_permission(permission_code, session, user)

    return _dep


# ---------------------------------------------------------------------------
# Dashboard widget registry
# ---------------------------------------------------------------------------

DASHBOARD_WIDGETS: list[dict] = [
    {"key": "my_profile", "permission": None},
    {"key": "my_leave_balance", "permission": None},
    {"key": "pending_approvals", "permission": "leave.approve"},
    {"key": "team_leave_requests", "permission": "leave.approve"},
    {"key": "department_headcount", "permission": "employee.view", "min_scope": "department"},
    {"key": "unit_overview", "permission": "employee.view", "min_scope": "unit"},
    {"key": "payroll_summary", "permission": "salary_cost.view_unit"},
    {"key": "org_analytics", "permission": "employee.view", "min_scope": "organization"},
    {"key": "attendance_overview", "permission": "attendance.view_department", "min_scope": "department"},
    {"key": "system_health", "permission": "system.configure"},
]


async def get_visible_widgets(user: User, session: AsyncSession) -> list[str]:
    """Return list of widget keys the user is allowed to see."""
    user_permissions = await get_effective_permissions(user.id, session)
    user_max_scope = await get_max_scope_level(user.id, session)

    # Super Admin sees everything
    if user.is_superuser:
        return [w["key"] for w in DASHBOARD_WIDGETS]

    visible: list[str] = []
    for widget in DASHBOARD_WIDGETS:
        required_perm: str | None = widget.get("permission")
        if required_perm is None:
            visible.append(widget["key"])
            continue
        if required_perm not in user_permissions:
            continue
        min_scope: ScopeLevel | None = widget.get("min_scope")  # type: ignore[assignment]
        if min_scope and not scope_satisfies(user_max_scope, min_scope):
            continue
        visible.append(widget["key"])

    return visible
