"""
core/employee_access.py — Row-level access scoping for employees.

Permissions answer *what* a user may do; this module answers *which
employees* the action applies to. The hierarchy is:

    organization  (Super Admin / HR_ADMIN fallback)
      └── unit              (HR_ADMIN sees their unit)
            └── department  (DEPARTMENT_MANAGER sees their department)

`EmployeeAccessScope` is the resulting view: either the whole
organization, or a set of unit/department IDs.
"""

from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_user_permissions
from db.models import Employee, User
from repositories.employee_repo import EmployeeRepository


@dataclass
class EmployeeAccessScope:
    """The slice of the organization a user is allowed to see.

    `organization=True` grants everything. Otherwise access is limited to
    the listed unit and department IDs (either may be empty).
    """

    organization: bool = False
    unit_ids: set[int] = field(default_factory=set)
    department_ids: set[int] = field(default_factory=set)

    def include(self, other: "EmployeeAccessScope") -> None:
        """Merge `other` into this scope (used when a route accepts several permissions)."""
        self.organization = self.organization or other.organization
        self.unit_ids.update(other.unit_ids)
        self.department_ids.update(other.department_ids)

    def allows(self, employee: Employee) -> bool:
        """Is this employee visible within the scope?"""
        return (
            self.organization
            or (employee.unit_id is not None and employee.unit_id in self.unit_ids)
            or (
                employee.department_id is not None
                and employee.department_id in self.department_ids
            )
        )


async def get_current_employee(user: User, session: AsyncSession) -> Employee:
    """Return the Employee profile linked to this login, or 403 if none."""
    employee = await EmployeeRepository(session).get_by_user_id(user.id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The signed-in user is not linked to an employee profile",
        )
    return employee


async def get_permission_scope(
    user: User,
    permission_code: str,
    session: AsyncSession,
) -> EmployeeAccessScope:
    """Translate a user's role into a concrete visibility scope.

    - Super Admin → whole organization.
    - HR_ADMIN → their own unit.
    - DEPARTMENT_MANAGER → their own department.
    - Anyone lacking the permission entirely → an empty scope.

    The returned scope is *not* merged with other permissions; callers that
    accept multiple permission codes merge scopes themselves via `include`.
    """
    if user.is_superuser:
        return EmployeeAccessScope(organization=True)
    employee = await get_current_employee(user, session)
    permissions = set(await get_user_permissions(user, session))
    requested = {permission_code} if isinstance(permission_code, str) else set(permission_code)
    if not permissions.intersection(requested):
        return EmployeeAccessScope()
    role = employee.role
    if role == "HR_ADMIN":
        return EmployeeAccessScope(unit_ids={employee.unit_id} if employee.unit_id else set())
    if role == "DEPARTMENT_MANAGER":
        return EmployeeAccessScope(department_ids={employee.department_id} if employee.department_id else set())
    return EmployeeAccessScope()


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
