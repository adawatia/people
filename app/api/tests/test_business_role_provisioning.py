"""Provisioning and audit of business roles / access scope.

Complements ``test_business_role_authorization.py`` (which is pure) by exercising
the real write paths:

* a legacy ``role``-only create still produces coherent scope columns (unit HR
  admin, department manager, organization owner);
* an administrator/ERP update can promote an HR admin to **organization** scope
  without changing the role, which is the only supported way to express
  organization-level HR;
* both events land in the existing append-only ``audit_logs`` table.
"""

import asyncio
import selectors
import sys
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from core.database import async_session_maker
from core.employee_access import scope_for_employee
from db.models import AuditLog, Department, Designation, Employee, Organization, Unit
from schemas.employees import EmployeeCreate, EmployeeUpdate
from services.employee_service import EmployeeService


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


@pytest.fixture
def unique_suffix():
    return uuid.uuid4().hex[:6]


async def _structure(session, suffix: str):
    org = await session.scalar(select(Organization).order_by(Organization.id.asc()))
    if org is None:
        org = Organization(name=f"Org Roles {suffix}", short_name=f"OR_{suffix}")
        session.add(org)
        await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit {suffix}", code=f"UR_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Dept {suffix}", code=f"DR_{suffix}")
    desig = Designation(name=f"Analyst {suffix}", code=f"AR_{suffix}")
    session.add_all([dept, desig])
    await session.flush()
    return unit, dept, desig


async def _audit_actions(session, employee_id: int) -> list[str]:
    rows = await session.execute(
        select(AuditLog.action).where(
            AuditLog.entity_type == "employee",
            AuditLog.entity_id == str(employee_id),
        )
    )
    return [row[0] for row in rows]


def test_legacy_role_only_create_produces_coherent_scope_columns_and_an_audit_row(unique_suffix):
    """An integration that only knows ``role`` still gets unit HR, not org HR."""

    async def _test():
        async with async_session_maker() as session:
            unit, dept, desig = await _structure(session, unique_suffix)
            service = EmployeeService(session)

            created = await service.create_employee(
                EmployeeCreate(
                    first_name="Uma",
                    last_name="Hr",
                    employee_code=f"HR_{unique_suffix}",
                    official_email=f"uma_{unique_suffix}@example.com",
                    role="HR_ADMIN",
                    unit_id=unit.id,
                    department_id=dept.id,
                    designation_id=desig.id,
                )
            )

            employee = await session.get(Employee, created.id)
            # The legacy mirror survives for ERP consumers...
            assert employee.role == "HR_ADMIN"
            # ...while the explicit columns carry the resolved assignment.
            assert employee.business_role == "HR_ADMIN"
            assert employee.access_scope == "UNIT"
            assert employee.access_scope_id == unit.id
            # A unit HR admin must not accidentally have organization reach.
            assert scope_for_employee(employee).unit_ids == {unit.id}

            assert await _audit_actions(session, created.id) == ["EMPLOYEE_ROLE_GRANTED"]

    run_async(_test())


def test_promoting_hr_to_organization_scope_keeps_the_role_and_is_audited(unique_suffix):
    """Organization HR is HR_ADMIN + ORGANIZATION scope — never a different role."""

    async def _test():
        async with async_session_maker() as session:
            unit, dept, desig = await _structure(session, unique_suffix)
            service = EmployeeService(session)

            created = await service.create_employee(
                EmployeeCreate(
                    first_name="Opal",
                    last_name="Org",
                    employee_code=f"OPS_{unique_suffix}",
                    official_email=f"opal_{unique_suffix}@example.com",
                    role="HR_ADMIN",
                    unit_id=unit.id,
                    department_id=dept.id,
                    designation_id=desig.id,
                )
            )

            updated = await service.update_employee(
                created.id,
                EmployeeUpdate(access_scope="ORGANIZATION"),
            )

            employee = await session.get(Employee, created.id)
            assert employee.role == "HR_ADMIN"
            assert employee.business_role == "HR_ADMIN"
            assert employee.access_scope == "ORGANIZATION"
            assert employee.access_scope_id is None
            assert updated.business_role == "HR_ADMIN"
            assert updated.access_scope == "ORGANIZATION"
            assert scope_for_employee(employee).organization is True

            actions = await _audit_actions(session, created.id)
            assert actions == ["EMPLOYEE_ROLE_GRANTED", "EMPLOYEE_ROLE_CHANGED"]

    run_async(_test())


def test_transferring_a_unit_hr_admin_moves_their_scope_with_them(unique_suffix):
    """A transfer must not leave the HR admin scoped to the unit they left."""

    async def _test():
        async with async_session_maker() as session:
            unit, dept, desig = await _structure(session, unique_suffix)
            other_unit = Unit(
                organization_id=unit.organization_id,
                name=f"Unit B {unique_suffix}",
                code=f"UB_{unique_suffix}",
            )
            session.add(other_unit)
            await session.flush()

            other_dept = Department(
                unit_id=other_unit.id, name=f"Dept B {unique_suffix}", code=f"DB_{unique_suffix}"
            )
            session.add(other_dept)
            await session.flush()

            # Capture plain ids: the service commits (and expires the ORM
            # objects) before we assert on them.
            original_unit_id = unit.id
            other_unit_id = other_unit.id
            other_dept_id = other_dept.id
            service = EmployeeService(session)
            created = await service.create_employee(
                EmployeeCreate(
                    first_name="Nina",
                    last_name="Hr",
                    employee_code=f"MOVE_{unique_suffix}",
                    official_email=f"nina_{unique_suffix}@example.com",
                    role="HR_ADMIN",
                    unit_id=original_unit_id,
                    department_id=dept.id,
                    designation_id=desig.id,
                )
            )

            await service.update_employee(
                created.id,
                EmployeeUpdate(unit_id=other_unit_id, department_id=other_dept_id),
            )

            employee = await session.get(Employee, created.id)
            assert employee.business_role == "HR_ADMIN"
            assert employee.access_scope == "UNIT"
            # The stored scope moved with the employee: no lingering reach over
            # the old unit, and unit identity is preserved.
            assert employee.access_scope_id == other_unit_id
            assert scope_for_employee(employee).unit_ids == {other_unit_id}
            assert (
                scope_for_employee(employee).allows(
                    SimpleNamespace(id=-1, unit_id=original_unit_id, department_id=None)
                )
                is False
            )
            # The scope change is auditable (§13).
            assert await _audit_actions(session, created.id) == ["EMPLOYEE_ROLE_GRANTED", "EMPLOYEE_ROLE_CHANGED"]

    run_async(_test())


def test_plain_employee_creation_writes_no_role_audit_row(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            unit, dept, desig = await _structure(session, unique_suffix)
            service = EmployeeService(session)

            created = await service.create_employee(
                EmployeeCreate(
                    first_name="Pat",
                    last_name="Plain",
                    employee_code=f"PLAIN_{unique_suffix}",
                    official_email=f"pat_{unique_suffix}@example.com",
                    unit_id=unit.id,
                    department_id=dept.id,
                    designation_id=desig.id,
                )
            )

            employee = await session.get(Employee, created.id)
            assert employee.business_role is None
            assert employee.access_scope == "SELF"
            assert await _audit_actions(session, created.id) == []

    run_async(_test())
