"""Business-role and access-scope primitives.

``Employee`` is the business identity.  An employee may *optionally* carry one
elevated business role, and the access scope says where that role applies.
This module is the single source of truth for both, so permission resolution
(``core.auth``) and row-level scope resolution (``core.employee_access``) can
never drift apart.

One employee has at most one elevated role; there are no role-assignment
tables, no per-user permissions and no deny overrides.  If those arrive later
they belong in this module.

Scope types and their meaning:

    SELF          the employee's own records only (implicit for every employee)
    DEPARTMENT    employees of one department
    UNIT          employees of one unit (across departments)
    ORGANIZATION  every employee in the organization

``Employee.role`` stays as a persisted compatibility column: the ERP writes it
and clients still read it.  ``role == "EMPLOYEE"`` now simply means "no
elevation".  Rows that predate the scope columns (or are written by an
integration that only knows ``role``) resolve through the same defaults, so
existing users keep exactly the access they had.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
HR_ADMIN = "HR_ADMIN"
ORGANIZATION_OWNER = "ORGANIZATION_OWNER"

# The compatibility value for "not elevated".
EMPLOYEE = "EMPLOYEE"

ELEVATED_BUSINESS_ROLES: tuple[str, ...] = (DEPARTMENT_MANAGER, HR_ADMIN, ORGANIZATION_OWNER)
ELEVATED_BUSINESS_ROLE_SET: frozenset[str] = frozenset(ELEVATED_BUSINESS_ROLES)

SCOPE_SELF = "SELF"
SCOPE_DEPARTMENT = "DEPARTMENT"
SCOPE_UNIT = "UNIT"
SCOPE_ORGANIZATION = "ORGANIZATION"

ACCESS_SCOPES: tuple[str, ...] = (SCOPE_SELF, SCOPE_DEPARTMENT, SCOPE_UNIT, SCOPE_ORGANIZATION)
ACCESS_SCOPE_SET: frozenset[str] = frozenset(ACCESS_SCOPES)

# Which scope types each role may be assigned.  HR is the only role that is
# explicitly configured for either one unit or the whole organization; a
# department manager is department scoped and an organization owner is always
# organization scoped (executive analytics, not operational HR).
ROLE_SCOPE_TYPES: dict[str, frozenset[str]] = {
    DEPARTMENT_MANAGER: frozenset({SCOPE_DEPARTMENT}),
    HR_ADMIN: frozenset({SCOPE_UNIT, SCOPE_ORGANIZATION}),
    ORGANIZATION_OWNER: frozenset({SCOPE_ORGANIZATION}),
}

# Fields that make up an employee's authorization identity on the write paths.
ROLE_COLUMN_FIELDS: frozenset[str] = frozenset({"role", "business_role", "access_scope", "access_scope_id"})


@dataclass(frozen=True)
class BusinessAccess:
    """Resolved authorization identity: optional business role + access scope."""

    business_role: str | None
    scope_type: str
    scope_id: int | None

    @property
    def is_elevated(self) -> bool:
        return self.business_role is not None


def normalize_scope_value(value: str | None) -> str | None:
    """Uppercase/trim a role or scope value; empty becomes ``None``."""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def resolve_business_role(employee: Any) -> str | None:
    """Return the employee's elevated business role, if any.

    ``Employee.business_role`` is authoritative when it holds an elevated
    value.  Otherwise the legacy ``Employee.role`` column is consulted, which
    keeps every pre-refactor row (and every ERP integration that only knows
    ``role``) working unchanged.
    """
    explicit = normalize_scope_value(getattr(employee, "business_role", None))
    if explicit in ELEVATED_BUSINESS_ROLE_SET:
        return explicit
    legacy = normalize_scope_value(getattr(employee, "role", None))
    if legacy in ELEVATED_BUSINESS_ROLE_SET:
        return legacy
    return None


def default_access_scope(
    business_role: str | None,
    *,
    unit_id: int | None,
    department_id: int | None,
) -> tuple[str, int | None]:
    """The scope a role falls back to when no explicit scope is configured.

    This is what keeps the migration backward compatible: an HR admin without
    an explicit scope is unit scoped on their own unit, and a department
    manager is scoped to their own department.
    """
    if business_role == HR_ADMIN:
        return SCOPE_UNIT, unit_id
    if business_role == DEPARTMENT_MANAGER:
        return SCOPE_DEPARTMENT, department_id
    if business_role == ORGANIZATION_OWNER:
        return SCOPE_ORGANIZATION, None
    return SCOPE_SELF, None


def resolve_business_access(employee: Any) -> BusinessAccess:
    """Resolve business role + access scope for an employee record.

    An explicit scope is honoured only when it is legal for the role; anything
    else (stale value, scope from another role, missing identifier) falls back
    to the role default.  A missing ``access_scope_id`` resolves to the
    employee's own ``unit_id`` / ``department_id``, so a transfer keeps working
    without re-provisioning.

    An organization owner is always organization scoped: the role *is*
    organization-wide analytics, so a narrower scope cannot be expressed.
    """
    business_role = resolve_business_role(employee)
    if business_role is None:
        return BusinessAccess(None, SCOPE_SELF, None)

    scope_type = normalize_scope_value(getattr(employee, "access_scope", None))
    scope_id = getattr(employee, "access_scope_id", None)
    if scope_type not in ROLE_SCOPE_TYPES[business_role]:
        scope_type, scope_id = default_access_scope(
            business_role,
            unit_id=getattr(employee, "unit_id", None),
            department_id=getattr(employee, "department_id", None),
        )
    elif scope_type == SCOPE_ORGANIZATION:
        scope_id = None  # organization scope covers the whole organization by definition
    elif scope_id is None:
        target = "unit_id" if scope_type == SCOPE_UNIT else "department_id"
        scope_id = getattr(employee, target, None)

    return BusinessAccess(business_role, scope_type, scope_id)


def role_columns(
    business_role: str | None,
    *,
    access_scope: str | None = None,
    access_scope_id: int | None = None,
    unit_id: int | None = None,
    department_id: int | None = None,
) -> dict[str, object]:
    """Persisted column values for an elevated business role (or none).

    Returns the legacy ``role`` mirror together with the explicit
    ``business_role`` / ``access_scope`` / ``access_scope_id`` columns.
    """
    elevated = normalize_scope_value(business_role)
    if elevated not in ELEVATED_BUSINESS_ROLE_SET:
        return {"role": EMPLOYEE, "business_role": None, "access_scope": SCOPE_SELF, "access_scope_id": None}

    scope_type = normalize_scope_value(access_scope)
    if scope_type not in ROLE_SCOPE_TYPES[elevated]:
        scope_type, scope_id = default_access_scope(elevated, unit_id=unit_id, department_id=department_id)
    elif scope_type == SCOPE_ORGANIZATION:
        scope_id = None
    else:
        scope_id = access_scope_id or (unit_id if scope_type == SCOPE_UNIT else department_id)

    return {
        "role": elevated,
        "business_role": elevated,
        "access_scope": scope_type,
        "access_scope_id": scope_id,
    }


def merge_role_columns(employee: Any, updates: Mapping[str, Any]) -> dict[str, object]:
    """Merge a partial role/scope update with the employee's current assignment.

    ``role`` remains the field the ERP writes: an update that only sends
    ``role`` still produces coherent scope columns, one that only moves an HR
    admin from unit to organization scope keeps the HR role, and an explicit
    ``business_role`` of ``None`` or ``"EMPLOYEE"`` removes the elevation.

    A transfer also keeps the assignment coherent: moving an employee to
    another unit (or department) moves a UNIT/DEPARTMENT scope with them, so a
    unit HR admin can never keep reach over the unit they left.  A caller that
    passes ``access_scope_id`` explicitly still wins — that is how a scope
    deliberately different from the employee's own unit is provisioned.
    """
    current = resolve_business_access(employee)
    if "business_role" in updates:
        candidate = normalize_scope_value(updates.get("business_role"))
    elif "role" in updates:
        candidate = normalize_scope_value(updates.get("role"))
    else:
        candidate = current.business_role
    business_role = candidate if candidate in ELEVATED_BUSINESS_ROLE_SET else None

    unit_id = updates.get("unit_id", getattr(employee, "unit_id", None))
    department_id = updates.get("department_id", getattr(employee, "department_id", None))
    access_scope = updates.get("access_scope") if "access_scope" in updates else current.scope_type
    scope_type = normalize_scope_value(access_scope)

    if "access_scope_id" in updates:
        access_scope_id = updates.get("access_scope_id")
    elif scope_type == current.scope_type and business_role == current.business_role:
        # Unchanged assignment: keep an explicitly pinned scope id, but follow a
        # move of the employee's own unit/department.
        moved_unit = "unit_id" in updates and updates.get("unit_id") != getattr(employee, "unit_id", None)
        moved_department = "department_id" in updates and updates.get("department_id") != getattr(
            employee, "department_id", None
        )
        if scope_type == SCOPE_UNIT and moved_unit:
            access_scope_id = unit_id
        elif scope_type == SCOPE_DEPARTMENT and moved_department:
            access_scope_id = department_id
        else:
            access_scope_id = current.scope_id
    else:
        # Role or scope type changed: any previous scope id belongs to the old
        # assignment and must not be carried over.
        access_scope_id = None

    return role_columns(
        business_role,
        access_scope=access_scope,
        access_scope_id=access_scope_id,
        unit_id=unit_id,
        department_id=department_id,
    )
