"""Negative authorization tests: scope boundaries, superadmin isolation, unenforced permissions.

These tests require a PostgreSQL test database (DATABASE_URL ending in _test).
They verify that:
* A department manager cannot see employees outside their department.
* A unit HR admin cannot see employees outside their unit.
* A plain employee cannot list other employees.
* Super Admin cannot access workforce endpoints (no employee row scope).
* Permission codes listed in ROLE_PERMISSIONS but not enforced by any endpoint
  are documented as unenforced, not treated as vulnerabilities by the test.
"""
from __future__ import annotations

import asyncio
import selectors
import sys
import uuid

import pytest
from sqlalchemy import select

from core.auth import (
    BASE_EMPLOYEE_PERMISSIONS,
    ROLE_PERMISSIONS,
    effective_permissions,
)
from core.business_roles import (
    DEPARTMENT_MANAGER,
    HR_ADMIN,
)
from core.database import async_session_maker
from core.employee_access import (
    require_employee_access,
    scope_for_employee,
)
from db.models import (
    Department,
    Employee,
    Organization,
    Unit,
    User,
)


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


async def _make_user(session, tag, **kwargs):
    """Create an active login with the columns the schema requires.

    ``users.email`` and ``users.hashed_password`` are NOT NULL and
    ``users.username`` is unique, so each call supplies all three; sharing one
    fixed username also collided with the seeded Super Admin account. The
    password value is a placeholder because these tests never sign in.
    """
    suffix = uuid.uuid4().hex[:10]
    user = User(
        username=f"{tag}_{suffix}",
        email=f"{tag}.{suffix}@example.test",
        hashed_password="test-only-placeholder",
        is_active=True,
        **kwargs,
    )
    session.add(user)
    await session.flush()
    return user


def _fresh(suffix: str) -> str:
    """Make a fixture suffix unique per call.

    Unit, Department and Employee codes are unique columns, so a fixed literal
    suffix made the second run of the suite fail with a duplicate key.
    """
    return f"{suffix}-{uuid.uuid4().hex[:8]}"


async def _make_org_unit_dept(session, suffix):
    suffix = _fresh(suffix)
    # The schema allows exactly one organization (uq_organizations_singleton_key),
    # so every test reuses the existing one instead of inserting its own. A
    # per-test organization made the second test in this file fail with a
    # unique violation rather than exercising authorization at all.
    org = await session.scalar(select(Organization).order_by(Organization.id))
    if org is None:
        org = Organization(name=f"Org Auth {suffix}", short_name=f"OA_{suffix}")
        session.add(org)
        await session.flush()
    unit = Unit(organization_id=org.id, name=f"Unit Auth {suffix}", code=f"UA_{suffix}")
    session.add(unit)
    await session.flush()
    dept = Department(unit_id=unit.id, name=f"Dept Auth {suffix}", code=f"DA_{suffix}")
    session.add(dept)
    await session.flush()
    return org, unit, dept


async def _make_employee(session, suffix, unit_id, dept_id, user_id=None, business_role=None, access_scope=None, access_scope_id=None):
    suffix = _fresh(suffix)
    emp = Employee(
        first_name="Test",
        last_name="User",
        employee_code=f"AUTH_{suffix}",
        official_email=f"auth_{suffix}@example.com",
        unit_id=unit_id,
        department_id=dept_id,
        employment_type="FULL_TIME",
        status="ACTIVE",
        business_role=business_role,
        access_scope=access_scope or "SELF",
        access_scope_id=access_scope_id,
    )
    session.add(emp)
    await session.flush()
    if user_id is not None:
        emp.user_id = user_id
    await session.flush()
    return emp


def test_department_manager_scope_only_see_their_department():
    async def _test():
        async with async_session_maker() as session:
            org, unit, dept_a = await _make_org_unit_dept(session, "dept")
            dept_b = Department(unit_id=unit.id, name="Other Dept", code=_fresh("OD"))
            session.add(dept_b)
            await session.flush()

            mgr_dept_a = await _make_employee(session, "mgrA", unit.id, dept_a.id, business_role=DEPARTMENT_MANAGER, access_scope="DEPARTMENT", access_scope_id=dept_a.id)
            emp_dept_a = await _make_employee(session, "empA", unit.id, dept_a.id)
            emp_dept_b = await _make_employee(session, "empB", unit.id, dept_b.id)

            await session.commit()

            # Department manager of dept_a: can see emp_dept_a, cannot see emp_dept_b.
            scope = scope_for_employee(mgr_dept_a)
            assert scope.allows(emp_dept_a) is True
            assert scope.allows(emp_dept_b) is False

            # require_employee_access enforces the same boundary.
            user = await _make_user(session, "mgr_dept_a")
            mgr_dept_a.user_id = user.id
            await session.commit()

            # require_employee_access takes a permission *code*, not a role name:
            # passing the role silently resolved to an empty scope, so the
            # allowed case raised 403 and the denied case proved nothing.
            await require_employee_access(user, emp_dept_a, "employee.view", session)
            with pytest.raises(Exception) as exc_info:
                await require_employee_access(user, emp_dept_b, "employee.view", session)
            assert exc_info.value.status_code == 403

    run_async(_test())


def test_unit_hr_scope_only_see_their_unit():
    async def _test():
        async with async_session_maker() as session:
            org, unit_a, dept_a = await _make_org_unit_dept(session, "unitA")
            unit_b = Unit(organization_id=org.id, name="Other Unit", code=_fresh("OU"))
            session.add(unit_b)
            await session.flush()
            dept_b = Department(unit_id=unit_b.id, name="Dept in Other Unit", code=_fresh("DO"))
            session.add(dept_b)
            await session.flush()

            hr_unit_a = await _make_employee(session, "hrA", unit_a.id, dept_a.id, business_role=HR_ADMIN, access_scope="UNIT", access_scope_id=unit_a.id)
            emp_unit_a = await _make_employee(session, "empUA", unit_a.id, dept_a.id)
            emp_unit_b = await _make_employee(session, "empUB", unit_b.id, dept_b.id)

            user = await _make_user(session, "hr_unit_a")
            hr_unit_a.user_id = user.id
            await session.commit()

            scope = scope_for_employee(hr_unit_a)
            assert scope.allows(emp_unit_a) is True
            assert scope.allows(emp_unit_b) is False

            await require_employee_access(user, emp_unit_a, "employee.view", session)
            with pytest.raises(Exception) as exc_info:
                await require_employee_access(user, emp_unit_b, "employee.view", session)
            assert exc_info.value.status_code == 403

    run_async(_test())


def test_plain_employee_cannot_see_other_employees():
    async def _test():
        async with async_session_maker() as session:
            org, unit, dept = await _make_org_unit_dept(session, "plain")
            emp_self = await _make_employee(session, "self", unit.id, dept.id)
            emp_other = await _make_employee(session, "other", unit.id, dept.id)

            user = await _make_user(session, "plain_employee")
            emp_self.user_id = user.id
            await session.commit()

            scope = scope_for_employee(emp_self)
            assert scope.self_only is True
            assert scope.allows(emp_self) is True
            assert scope.allows(emp_other) is False

            # A plain employee has BASE_EMPLOYEE_PERMISSIONS but not employee.view.
            perms = effective_permissions(None)  # None business_role = plain employee
            assert "employee.view" not in perms

    run_async(_test())


def test_super_admin_has_no_workforce_row_scope():
    async def _test():
        async with async_session_maker() as session:
            org, unit, dept = await _make_org_unit_dept(session, "sa")
            emp = await _make_employee(session, "sa_emp", unit.id, dept.id)
            superuser = await _make_user(session, "superadmin", is_superuser=True)

            # Super Admin has no workforce row scope (empty scope).
            from core.employee_access import get_employee_scope
            scope = await get_employee_scope(superuser, session)
            assert scope.organization is False
            assert scope.unit_ids == set()
            assert scope.department_ids == set()
            assert scope.employee_ids == set()
            assert not scope.allows(emp)

    run_async(_test())


def test_unenforced_permissions_are_listed():
    """ROLE_PERMISSIONS may contain codes that no endpoint currently enforces.

    This test documents the gap rather than asserting it is a vulnerability.
    The test passes if the code exists in ROLE_PERMISSIONS; the *absence* of an
    enforcing endpoint is verified manually against the routers.
    """
    # From the change list (P1 #6): these are granted but may not be enforced.
    possibly_unenforced = {
        "employee.view_self",
        "attendance.view_self",
        "leave.view_self",
        "overtime.view_self",
        "shift.view_self",
        "reports.view",
        "reports.overtime",
        "reports.salary_cost",
        "salary_cost.view_unit",
        "salary_cost.view_department",
        "audit.view",
        "user.view",
        "user.create",
        "user.update",
        "user.deactivate",
        "employee.update",
        "employee.deactivate",
        "overtime.view",
    }

    # Every code that is *not* in any role bundle is not a concern here.
    all_granted = set()
    for bundle in ROLE_PERMISSIONS.values():
        all_granted |= bundle
    all_granted |= BASE_EMPLOYEE_PERMISSIONS

    missing_from_roles = possibly_unenforced - all_granted
    assert not missing_from_roles, f"These codes are listed as possibly unenforced but are not granted to any role: {missing_from_roles}"

    # Codes that ARE granted but may lack an enforcing endpoint:
    granted_but_maybe_unenforced = possibly_unenforced & all_granted
    assert granted_but_maybe_unenforced, (
        "Expected at least some codes in the 'granted but possibly unenforced' list; "
        "if this list is empty the ROLE_PERMISSIONS catalogue changed and this test "
        "should be revisited against the routers."
    )

    # This is documentation: the test records which codes exist but does not
    # assert enforcement.  Enforcement is verified by reading the routers.
    # Print for the test report so a reviewer can cross-check against routers.
    print(f"\n=== Authorization scoping: granted-but-possibly-unenforced permissions ===\n{sorted(granted_but_maybe_unenforced)}\n")
