"""Authorization matrix for the business-role + access-scope model.

``Employee`` is the business identity; an elevated *business role* is optional
and the *access scope* says where that role applies.  The matrix asserted here
is the contract from the refactor:

    plain employee      base permissions,                SELF scope
    DEPARTMENT_MANAGER  base + manager bundle,           DEPARTMENT scope
    HR_ADMIN (UNIT)     base + HR bundle,                UNIT scope
    HR_ADMIN (ORG)      the *same* HR bundle,            ORGANIZATION scope
    ORGANIZATION_OWNER  base + analytics bundle,         ORGANIZATION scope
    Super Admin         unchanged (HR bundle,            ORGANIZATION scope)

The important invariants are that organization HR is the HR role with an
organization scope (never ``ORGANIZATION_OWNER``), that the Organization Owner
gains no operational HR or manager approval capability, and that a unit-scoped
HR admin stays confined to their unit.

These tests are pure: they patch the two database lookups, so they run in
milliseconds and do not need a database.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import employee_access
from core.auth import BASE_EMPLOYEE_PERMISSIONS, effective_permissions
from core.business_roles import (
    DEPARTMENT_MANAGER,
    EMPLOYEE,
    HR_ADMIN,
    ORGANIZATION_OWNER,
    SCOPE_DEPARTMENT,
    SCOPE_ORGANIZATION,
    SCOPE_SELF,
    SCOPE_UNIT,
    merge_role_columns,
    resolve_business_access,
)

# Permissions that only operational HR holds.
HR_ONLY_PERMISSIONS = {"attendance.correct", "attendance.process", "user.create", "employee.update"}
# Permissions that only a people manager holds.
MANAGER_ONLY_PERMISSIONS = {"leave.approve", "work_arrangement.approve", "overtime.approve"}
# Analytics permission that is unique to the Organization Owner.
OWNER_ONLY_PERMISSIONS = {"dashboard.view_organization"}


def employee(**overrides) -> SimpleNamespace:
    """Build an employee record; unknown scope columns default like un-migrated rows."""
    fields = {
        "id": 1,
        "user_id": 1,
        "role": EMPLOYEE,
        "business_role": None,
        "access_scope": SCOPE_SELF,
        "access_scope_id": None,
        "unit_id": None,
        "department_id": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def plain_employee(**overrides) -> SimpleNamespace:
    return employee(**overrides)


def department_manager(**overrides) -> SimpleNamespace:
    return employee(
        **{
            "id": 2,
            "user_id": 2,
            "role": DEPARTMENT_MANAGER,
            "business_role": DEPARTMENT_MANAGER,
            "access_scope": SCOPE_DEPARTMENT,
            "access_scope_id": 20,
            "department_id": 20,
            "unit_id": 7,
            **overrides,
        }
    )


def unit_hr(**overrides) -> SimpleNamespace:
    return employee(
        **{
            "id": 3,
            "user_id": 3,
            "role": HR_ADMIN,
            "business_role": HR_ADMIN,
            "access_scope": SCOPE_UNIT,
            "access_scope_id": 7,
            "unit_id": 7,
            **overrides,
        }
    )


def organization_hr(**overrides) -> SimpleNamespace:
    """Organization HR: the HR role with organization scope, never a unit."""
    return employee(
        **{
            "id": 4,
            "user_id": 4,
            "role": HR_ADMIN,
            "business_role": HR_ADMIN,
            "access_scope": SCOPE_ORGANIZATION,
            "access_scope_id": None,
            "unit_id": None,
            "department_id": None,
            **overrides,
        }
    )


def organization_owner(**overrides) -> SimpleNamespace:
    return employee(
        **{
            "id": 5,
            "user_id": 5,
            "role": ORGANIZATION_OWNER,
            "business_role": ORGANIZATION_OWNER,
            "access_scope": SCOPE_ORGANIZATION,
            "access_scope_id": None,
            **overrides,
        }
    )


def user(user_id: int = 1, *, is_superuser: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, is_superuser=is_superuser)


def target_employee(employee_id: int, *, unit_id: int | None, department_id: int | None = None) -> SimpleNamespace:
    """An employee record being acted on (its ``user_id`` is unrelated to the actor's)."""
    return SimpleNamespace(id=employee_id, user_id=9000 + employee_id, unit_id=unit_id, department_id=department_id)


def patch_identity(monkeypatch, actor_employee: SimpleNamespace) -> None:
    """Patch the two DB lookups so the actor resolves without a database."""
    monkeypatch.setattr(employee_access, "get_current_employee", AsyncMock(return_value=actor_employee))
    monkeypatch.setattr(
        employee_access,
        "get_user_permissions",
        AsyncMock(return_value=sorted(effective_permissions(actor_employee.business_role))),
    )


async def scope_for(actor: SimpleNamespace, permission: str) -> employee_access.EmployeeAccessScope:
    return await employee_access.get_permission_scope(user(actor.user_id), permission, AsyncMock())


# ── Plain employee: base permissions and self scope ───────────────────────────


def test_plain_employee_holds_exactly_the_base_permission_set():
    assert effective_permissions(None) == BASE_EMPLOYEE_PERMISSIONS


@pytest.mark.parametrize("permission", sorted(HR_ONLY_PERMISSIONS | MANAGER_ONLY_PERMISSIONS | OWNER_ONLY_PERMISSIONS))
def test_plain_employee_holds_no_elevated_permission(permission):
    assert permission not in effective_permissions(None)


def test_plain_employee_scope_is_self_only_and_never_organization():
    scope = employee_access.scope_for_employee(plain_employee(id=11))

    assert scope.self_only is True
    assert scope.organization is False
    assert scope.allows(target_employee(11, unit_id=None)) is True
    assert scope.allows(target_employee(12, unit_id=None)) is False


@pytest.mark.asyncio
async def test_plain_employee_cannot_act_on_another_employee(monkeypatch):
    patch_identity(monkeypatch, plain_employee(id=11, unit_id=7))

    with pytest.raises(HTTPException) as exc_info:
        await employee_access.require_employee_access(
            user(11), target_employee(12, unit_id=99), ("attendance.view_self",), AsyncMock()
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_self_service_bypass_still_covers_the_callers_own_record(monkeypatch):
    """``allow_self`` must keep working for an employee with no elevation."""
    patch_identity(monkeypatch, plain_employee(id=21, user_id=21))

    await employee_access.require_employee_access(
        user(21),
        SimpleNamespace(id=21, user_id=21, unit_id=None, department_id=None),
        "attendance.view_self",
        AsyncMock(),
        allow_self=True,
    )


@pytest.mark.asyncio
async def test_plain_employee_gets_no_scope_from_an_hr_permission(monkeypatch):
    """A base employee who somehow asks for an HR permission sees nothing."""
    patch_identity(monkeypatch, plain_employee(id=31, unit_id=7))

    scope = await employee_access.get_permission_scope(user(31), "attendance.correct", AsyncMock())

    assert scope.organization is False
    assert scope.unit_ids == set()
    assert scope.allows(target_employee(32, unit_id=7)) is False


# ── Department manager ────────────────────────────────────────────────────────


def test_department_manager_adds_manager_permissions_on_top_of_base():
    permissions = effective_permissions(DEPARTMENT_MANAGER)

    assert BASE_EMPLOYEE_PERMISSIONS <= permissions
    assert MANAGER_ONLY_PERMISSIONS <= permissions
    assert permissions.isdisjoint(HR_ONLY_PERMISSIONS)


def test_department_manager_is_scoped_to_their_department():
    scope = employee_access.scope_for_employee(department_manager())

    assert scope.organization is False
    assert scope.department_ids == {20}
    assert scope.unit_ids == set()
    assert scope.allows(target_employee(41, unit_id=7, department_id=20)) is True
    assert scope.allows(target_employee(42, unit_id=7, department_id=21)) is False


@pytest.mark.asyncio
async def test_department_manager_cannot_approve_outside_their_department(monkeypatch):
    patch_identity(monkeypatch, department_manager())

    await employee_access.require_employee_access(
        user(2), target_employee(41, unit_id=7, department_id=20), "leave.approve", AsyncMock()
    )

    with pytest.raises(HTTPException) as exc_info:
        await employee_access.require_employee_access(
            user(2), target_employee(42, unit_id=7, department_id=21), "leave.approve", AsyncMock()
        )

    assert exc_info.value.status_code == 403


def test_manager_scope_falls_back_to_their_own_department_id():
    """Rows written before the scope columns existed resolve to their department."""
    manager = SimpleNamespace(role=DEPARTMENT_MANAGER, unit_id=7, department_id=20)

    access = resolve_business_access(manager)

    assert (access.business_role, access.scope_type, access.scope_id) == (DEPARTMENT_MANAGER, SCOPE_DEPARTMENT, 20)


# ── Unit HR ───────────────────────────────────────────────────────────────────


def test_unit_hr_adds_hr_permissions_and_keeps_base():
    permissions = effective_permissions(HR_ADMIN)

    assert BASE_EMPLOYEE_PERMISSIONS <= permissions
    assert HR_ONLY_PERMISSIONS <= permissions
    assert "attendance.view_unit" in permissions


def test_unit_hr_is_scoped_to_the_assigned_unit():
    scope = employee_access.scope_for_employee(unit_hr())

    assert scope.organization is False
    assert scope.unit_ids == {7}
    assert scope.allows(target_employee(51, unit_id=7, department_id=20)) is True
    assert scope.allows(target_employee(52, unit_id=8, department_id=30)) is False


@pytest.mark.asyncio
async def test_unit_hr_may_act_inside_their_unit_and_not_outside_it(monkeypatch):
    patch_identity(monkeypatch, unit_hr())

    await employee_access.require_employee_access(
        user(3), target_employee(51, unit_id=7), "attendance.correct", AsyncMock()
    )

    with pytest.raises(HTTPException) as exc_info:
        await employee_access.require_employee_access(
            user(3), target_employee(52, unit_id=8), "attendance.correct", AsyncMock()
        )

    assert exc_info.value.status_code == 403


def test_unit_hr_transfer_follows_the_new_unit_when_no_scope_id_is_pinned():
    transfered = SimpleNamespace(
        role=HR_ADMIN, business_role=HR_ADMIN, access_scope=SCOPE_UNIT, access_scope_id=None, unit_id=9
    )

    access = resolve_business_access(transfered)

    assert (access.scope_type, access.scope_id) == (SCOPE_UNIT, 9)


# ── Organization HR ───────────────────────────────────────────────────────────


def test_organization_hr_has_the_same_permission_bundle_as_unit_hr():
    """Only the scope differs — the role is the same, so capabilities are identical."""
    unit_access = resolve_business_access(unit_hr())
    org_access = resolve_business_access(organization_hr())

    assert effective_permissions(unit_access.business_role) == effective_permissions(org_access.business_role)
    assert unit_access.business_role == org_access.business_role == HR_ADMIN
    assert (unit_access.scope_type, org_access.scope_type) == (SCOPE_UNIT, SCOPE_ORGANIZATION)


def test_organization_hr_is_not_an_organization_owner():
    permissions = effective_permissions(HR_ADMIN)

    assert permissions.isdisjoint(OWNER_ONLY_PERMISSIONS)
    assert resolve_business_access(organization_hr()).business_role != ORGANIZATION_OWNER


def test_organization_hr_scope_covers_every_unit():
    scope = employee_access.scope_for_employee(organization_hr())

    assert scope.organization is True
    assert scope.allows(target_employee(61, unit_id=7)) is True
    assert scope.allows(target_employee(62, unit_id=8, department_id=42)) is True


@pytest.mark.asyncio
async def test_organization_hr_reaches_employees_in_any_unit(monkeypatch):
    patch_identity(monkeypatch, organization_hr())

    for unit_id in (7, 8, 9):
        await employee_access.require_employee_access(
            user(4), target_employee(60 + unit_id, unit_id=unit_id), "attendance.correct", AsyncMock()
        )


def test_missing_unit_does_not_silently_grant_organization_scope():
    """Organization HR must be configured explicitly, never inferred from a blank unit."""
    hr_without_unit = SimpleNamespace(
        role=HR_ADMIN, business_role=HR_ADMIN, access_scope=None, access_scope_id=None, unit_id=None
    )

    access = resolve_business_access(hr_without_unit)
    scope = employee_access.scope_for_employee(hr_without_unit)

    assert access.scope_type == SCOPE_UNIT
    assert access.scope_id is None
    assert scope.organization is False
    assert scope.unit_ids == set()
    assert scope.allows(target_employee(71, unit_id=7)) is False


# ── Organization Owner ────────────────────────────────────────────────────────


def test_organization_owner_keeps_organization_visibility_without_operational_permissions():
    permissions = effective_permissions(ORGANIZATION_OWNER)
    scope = employee_access.scope_for_employee(organization_owner())

    assert OWNER_ONLY_PERMISSIONS <= permissions
    assert permissions.isdisjoint(HR_ONLY_PERMISSIONS)
    assert permissions.isdisjoint(MANAGER_ONLY_PERMISSIONS)
    assert scope.organization is True


@pytest.mark.asyncio
async def test_organization_owner_cannot_perform_hr_operations(monkeypatch):
    """Organization-wide visibility is not an HR licence."""
    patch_identity(monkeypatch, organization_owner())

    scope = await scope_for(organization_owner(), "attendance.correct")

    assert scope.organization is False
    assert scope.allows(target_employee(81, unit_id=7)) is False


def test_organization_owner_scope_is_always_organization_even_if_a_narrower_scope_is_stored():
    owner = organization_owner(access_scope=SCOPE_UNIT, access_scope_id=7)

    access = resolve_business_access(owner)

    assert (access.scope_type, access.scope_id) == (SCOPE_ORGANIZATION, None)


# ── Super Admin ───────────────────────────────────────────────────────────────


def test_super_admin_keeps_the_hr_bundle_it_always_had():
    """``get_user_permissions`` resolves Super Admin through ``effective_permissions(HR_ADMIN)``."""
    assert HR_ONLY_PERMISSIONS <= effective_permissions(HR_ADMIN)
    assert BASE_EMPLOYEE_PERMISSIONS <= effective_permissions(HR_ADMIN)


@pytest.mark.asyncio
async def test_super_admin_has_no_business_permission_scope(monkeypatch):
    lookup = AsyncMock()
    monkeypatch.setattr(employee_access, "get_current_employee", lookup)

    scope = await employee_access.get_permission_scope(user(1, is_superuser=True), "attendance.correct", AsyncMock())

    assert scope == employee_access.EmployeeAccessScope()
    assert lookup.await_count == 0


@pytest.mark.asyncio
async def test_super_admin_has_no_workforce_scope(monkeypatch):
    monkeypatch.setattr(employee_access, "get_current_employee", AsyncMock())

    scope = await employee_access.get_employee_scope(user(1, is_superuser=True), AsyncMock())

    assert scope == employee_access.EmployeeAccessScope()


# ── Assignment path (ERP / employee administration) ───────────────────────────


def test_role_only_assignment_defaults_hr_to_their_unit():
    columns = merge_role_columns(SimpleNamespace(role=EMPLOYEE, unit_id=7, department_id=20), {"role": "HR_ADMIN"})

    assert columns == {"role": HR_ADMIN, "business_role": HR_ADMIN, "access_scope": SCOPE_UNIT, "access_scope_id": 7}


def test_an_explicit_business_role_wins_over_the_legacy_role_field():
    columns = merge_role_columns(
        SimpleNamespace(role=EMPLOYEE, unit_id=7, department_id=20),
        {"role": EMPLOYEE, "business_role": "HR_ADMIN"},
    )

    assert columns["role"] == HR_ADMIN
    assert columns["business_role"] == HR_ADMIN
    assert columns["access_scope"] == SCOPE_UNIT


def test_moving_hr_from_unit_to_organization_scope_keeps_the_hr_role():
    unit_scoped = SimpleNamespace(
        role=HR_ADMIN, business_role=HR_ADMIN, access_scope=SCOPE_UNIT, access_scope_id=7, unit_id=7, department_id=20
    )

    columns = merge_role_columns(unit_scoped, {"access_scope": "ORGANIZATION"})

    assert columns == {
        "role": HR_ADMIN,
        "business_role": HR_ADMIN,
        "access_scope": SCOPE_ORGANIZATION,
        "access_scope_id": None,
    }


def test_clearing_the_business_role_returns_the_employee_to_self_service():
    hr = SimpleNamespace(
        role=HR_ADMIN, business_role=HR_ADMIN, access_scope=SCOPE_UNIT, access_scope_id=7, unit_id=7, department_id=20
    )

    columns = merge_role_columns(hr, {"business_role": EMPLOYEE})

    assert columns == {"role": EMPLOYEE, "business_role": None, "access_scope": SCOPE_SELF, "access_scope_id": None}


def test_a_transfer_repairs_a_legacy_row_that_only_had_the_role_column():
    """Rows written before the scope columns existed are brought up to date."""
    legacy_hr = SimpleNamespace(
        role=HR_ADMIN, business_role=None, access_scope=SCOPE_SELF, access_scope_id=None, unit_id=7, department_id=20
    )

    columns = merge_role_columns(legacy_hr, {"unit_id": 9})

    assert columns == {"role": HR_ADMIN, "business_role": HR_ADMIN, "access_scope": SCOPE_UNIT, "access_scope_id": 9}


def test_an_explicitly_cleared_business_role_wins_over_a_stale_legacy_role():
    """Precedence on contradictory input is documented: the explicit field wins."""
    columns = merge_role_columns(
        SimpleNamespace(
            role=HR_ADMIN,
            business_role=HR_ADMIN,
            access_scope=SCOPE_UNIT,
            access_scope_id=7,
            unit_id=7,
            department_id=20,
        ),
        {"business_role": None, "role": HR_ADMIN},
    )

    assert columns == {"role": EMPLOYEE, "business_role": None, "access_scope": SCOPE_SELF, "access_scope_id": None}


def test_assigning_a_scope_that_does_not_belong_to_the_role_falls_back_to_the_default():
    """A department manager can never be silently granted unit or organization reach."""
    columns = merge_role_columns(
        SimpleNamespace(role=EMPLOYEE, unit_id=7, department_id=20),
        {"role": DEPARTMENT_MANAGER, "access_scope": "ORGANIZATION"},
    )

    assert columns["access_scope"] == SCOPE_DEPARTMENT
    assert columns["access_scope_id"] == 20
