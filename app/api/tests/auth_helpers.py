"""Shared fixtures/helpers for the authentication test suites.

Kept out of ``conftest.py`` because this repository has none; pytest only
collects ``test_*.py``, so importing these from a test module is enough.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from fastapi_users.password import PasswordHelper
from sqlalchemy import select

from core.totp import totp_at
from db.models import Department, Designation, Employee, Organization, Unit, User, now_ist

# Meets the policy: 12+ chars, all classes, not common, not personal, zxcvbn >= 3.
PASSWORD = "Ridge7-Cobalt-Lantern"
NEW_PASSWORD = "Harbour9-Velvet-Marble"
API = "/api/v1"
password_helper = PasswordHelper()


def run_async(coro):
    """Run a coroutine in a fresh loop (Windows needs a selector loop)."""
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    return asyncio.run(coro)


@pytest.fixture
def unique_suffix():
    """Unique label per test so seeded rows never collide.

    Imported by each auth test module (pytest resolves fixtures from the test
    module's namespace, so an imported fixture is enough).
    """
    return uuid.uuid4().hex[:6]


def client() -> TestClient:
    from main import app

    return TestClient(app)


async def ensure_org_structure(session, suffix: str):
    """Reuse the singleton organization and add a fresh unit/department/designation."""
    org = await session.scalar(select(Organization).order_by(Organization.id.asc()))
    if org is None:
        org = Organization(name=f"Org Auth {suffix}", short_name=f"OA_{suffix}")
        session.add(org)
        await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit Auth {suffix}", code=f"UA_{suffix}")
    session.add(unit)
    await session.flush()

    department = Department(unit_id=unit.id, name=f"Dept Auth {suffix}", code=f"DA_{suffix}")
    designation = Designation(name=f"Engineer Auth {suffix}", code=f"EA_{suffix}")
    session.add_all([department, designation])
    await session.flush()
    return org, unit, department, designation


async def create_account(
    session,
    *,
    suffix: str,
    label: str = "emp",
    role: str = "EMPLOYEE",
    business_role: str | None = None,
    access_scope: str | None = None,
    access_scope_id: int | None = None,
    unit_id: int | None = None,
    department_id: int | None = None,
    is_superuser: bool = False,
    is_active: bool = True,
    password: str = PASSWORD,
) -> tuple[User, Employee]:
    """Create a login account plus its employee record."""
    user = User(
        # A normal-looking domain on purpose: pydantic's EmailStr rejects the
        # reserved special-use suffixes (``.test``, ``.invalid``, ...), and
        # /users/me validates this column.
        email=f"{label}.{suffix}@people-hrms.co.in",
        username=f"{label}.{suffix}",
        first_name=f"{label.title()}Auth",
        last_name="Tester",
        hashed_password=password_helper.hash(password),
        is_active=is_active,
        is_verified=True,
        is_superuser=is_superuser,
    )
    session.add(user)
    await session.flush()

    employee = Employee(
        user_id=user.id,
        employee_code=f"{label.upper()}_{suffix}"[:30],
        first_name=f"{label.title()}Auth",
        last_name="Tester",
        role=role,
        business_role=business_role,
        access_scope=access_scope or "SELF",
        access_scope_id=access_scope_id,
        unit_id=unit_id,
        department_id=department_id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(employee)
    await session.flush()
    await session.commit()
    return user, employee


def login(client_instance: TestClient, identity: str, password: str = PASSWORD, *, super_admin: bool = False):
    path = f"{API}/auth/super-admin/login" if super_admin else f"{API}/auth/employee/login"
    return client_instance.post(path, data={"username": identity, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refresh(client_instance: TestClient, refresh_token: str):
    return client_instance.post(f"{API}/auth/session/refresh", json={"refresh_token": refresh_token})


def as_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def next_code(secret: str, *, step: int = 1) -> str:
    """The code the authenticator will show ``step`` intervals from now.

    Codes are single-use, so a test that needs to authenticate twice with the
    same enrolled factor must move forward in time the way a real user does
    rather than resubmitting the code it just spent.
    """
    return totp_at(secret, now_ist() + timedelta(seconds=30 * step))


def activate_mfa(client_instance: TestClient, mfa_token: str, secret: str) -> dict:
    """Complete first-time enrolment and return the issued session payload."""
    response = client_instance.post(f"{API}/auth/mfa/activate", json={"mfa_token": mfa_token, "code": totp_at(secret, now_ist())})
    assert response.status_code == 200, response.text
    return response.json()
