"""
core/employee_access.py — Row-level access scoping for employees.

Permissions answer *what* a user may do (``core.auth``); this module answers
*which employees* the action applies to, by translating the employee's
business role + access scope (``core.business_roles``) into a row scope:

    SELF          → only the caller's own employee record
    DEPARTMENT    → {access_scope_id or department_id}
    UNIT          → {access_scope_id or unit_id}      (unit HR)
    ORGANIZATION  → every employee (org HR, Organization Owner, Super Admin)

`EmployeeAccessScope` is the resulting view.  Scope resolution stays
centralized here: routers never re-derive it from ``Employee.role``.
"""

from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_user_permissions
from core.business_roles import (
    SCOPE_DEPARTMENT,
    SCOPE_ORGANIZATION,
    SCOPE_UNIT,
    BusinessAccess,
    resolve_business_access,
)
from db.models import Employee, User
from repositories.employee_repo import EmployeeRepository


@dataclass
class EmployeeAccessScope:
    """The slice of the organization a user is allowed to see.

    `organization=True` grants everything. Otherwise access is limited to the
    listed employee, unit and department IDs (any may be empty);
    ``employee_ids`` carries SELF scope — the caller's own record.
    """

    organization: bool = False
    unit_ids: set[int] = field(default_factory=set)
    department_ids: set[int] = field(default_factory=set)
    employee_ids: set[int] = field(default_factory=set)

    def include(self, other: EmployeeAccessScope) -> None:
        """Merge `other` into this scope (used when a route accepts several permissions)."""
        self.organization = self.organization or other.organization
        self.unit_ids.update(other.unit_ids)
        self.department_ids.update(other.department_ids)
        self.employee_ids.update(other.employee_ids)

    def allows(self, employee: Employee) -> bool:
        """Is this employee visible within the scope?

        Read defensively so the check also works on a lightweight stand-in
        (a projection or a test double) that only carries the three ids.
        """
        employee_id = getattr(employee, "id", None)
        unit_id = getattr(employee, "unit_id", None)
        department_id = getattr(employee, "department_id", None)
        return (
            self.organization
            or (employee_id is not None and employee_id in self.employee_ids)
            or (unit_id is not None and unit_id in self.unit_ids)
            or (department_id is not None and department_id in self.department_ids)
        )

    @property
    def self_only(self) -> bool:
        """True when the scope grants no organization/unit/department reach.

        List endpoints read this as "restrict the query to the caller's own
        employee_id", which is also how a bare employee is handled.
        """
        return not (self.organization or self.unit_ids or self.department_ids)


async def get_current_employee(user: User, session: AsyncSession) -> Employee:
    """Return the Employee profile linked to this login, or 403 if none."""
    cache = session.info.setdefault("current_employees", {}) if hasattr(session, "info") else {}
    employee = cache.get(user.id)
    if employee is None:
        employee = await EmployeeRepository(session).get_by_user_id(user.id)
        if employee is not None:
            cache[user.id] = employee
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The signed-in user is not linked to an employee profile",
        )
    return employee


def scope_for_employee(employee: Employee) -> EmployeeAccessScope:
    """Translate an employee's business role + access scope into a row scope.

    This is the only place scope is derived from a role, so unit HR,
    organization HR, department managers and organization owners all resolve
    through the same rules.
    """
    access: BusinessAccess = resolve_business_access(employee)
    if access.scope_type == SCOPE_ORGANIZATION:
        return EmployeeAccessScope(organization=True)
    if access.scope_type == SCOPE_UNIT:
        return EmployeeAccessScope(unit_ids={access.scope_id} if access.scope_id else set())
    if access.scope_type == SCOPE_DEPARTMENT:
        return EmployeeAccessScope(department_ids={access.scope_id} if access.scope_id else set())
    return EmployeeAccessScope(employee_ids={employee.id})


async def get_employee_scope(user: User, session: AsyncSession) -> EmployeeAccessScope:
    """Row scope for the caller's business role, without a permission gate.

    Use this when the route already established the *permission* (for example
    with ``require_permission``) and only needs to know which records the
    caller may touch.  Super Admin keeps the break-glass organization scope.
    """
    if user.is_superuser:
        return EmployeeAccessScope(organization=True)
    return scope_for_employee(await get_current_employee(user, session))


async def get_permission_scope(
    user: User,
    permission_code: str,
    session: AsyncSession,
) -> EmployeeAccessScope:
    """Row scope for a user *for one permission code*.

    - Super Admin → whole organization.
    - Anyone lacking the permission → an empty scope (no access at all).
    - Otherwise the scope of their business role: SELF, DEPARTMENT, UNIT or
      ORGANIZATION (an HR admin's scope follows the assigned access scope).

    The returned scope is *not* merged with other permissions; callers that
    accept multiple permission codes merge scopes themselves via `include`.
    """
    if user.is_superuser:
        return EmployeeAccessScope(organization=True)
    employee = await get_current_employee(user, session)
    if not await _holds_permission(user, permission_code, session):
        return EmployeeAccessScope()
    return scope_for_employee(employee)


async def _holds_permission(
    user: User,
    permission_code: str | tuple[str, ...],
    session: AsyncSession,
) -> bool:
    """Does the user hold at least one of the requested permission codes?"""
    requested = {permission_code} if isinstance(permission_code, str) else set(permission_code)
    permissions = set(await get_user_permissions(user, session))
    return bool(permissions.intersection(requested))


async def require_employee_access(
    user: User,
    employee: Employee,
    permission_code: str | tuple[str, ...],
    session: AsyncSession,
    *,
    allow_self: bool = False,
) -> None:
    """Raise 403 unless `user` may act on `employee`.

    Pass a tuple of permission codes to grant access when *any* of them
    covers the target (e.g. ("attendance.view_self", "attendance.view_unit")).
    `allow_self=True` short-circuits for the user's own employee record,
    which is how employees see their own data without extra permissions.
    """
    if allow_self and employee.user_id == user.id:
        return
    permission_codes = (permission_code,) if isinstance(permission_code, str) else permission_code
    scope = EmployeeAccessScope()
    for code in permission_codes:
        scope.include(await get_permission_scope(user, code, session))
    if not scope.allows(employee):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this employee",
        )
