"""HTTP regression tests for the attendance correction surfaces.

Attendance corrections are raised by HR for ERP reconciliation, so:

* ``GET /attendance/corrections`` is scoped by ``attendance.correct`` — HR sees
  their unit, everyone else sees only their own requests (previously the scope
  permission was ``attendance.approve_correction``, which no role holds, so even
  HR silently saw only their own requests);
* the always-403 approve/reject endpoints are gone, because ERP confirmation is
  the approval.

They also pin the role/scope split: a *unit* HR admin and an *organization* HR
admin share the same HR permission bundle, so the only difference between them
is scope — the unit admin must be refused outside their unit while the
organization admin succeeds, with no role change involved.

These tests drive the real ASGI app with real bearer tokens.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from core.auth import get_jwt_strategy
from core.database import async_session_maker, auth_engine
from db.models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    Department,
    Employee,
    Organization,
    Unit,
    User,
)
from main import app


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    return asyncio.run(coro)


@pytest.fixture
def unique_suffix():
    return uuid.uuid4().hex[:6]


async def _seed(suffix: str) -> dict[str, object]:
    """Two units, a unit HR admin, an organization HR admin and two employees.

    Each unit holds one pending correction, so the two HR admins can be
    compared on identical data: same permission, different scope.
    """
    async with async_session_maker() as session:
        # The organization table is a singleton, so reuse whatever exists.
        org = await session.scalar(select(Organization).order_by(Organization.id.asc()))
        if org is None:
            org = Organization(name=f"Org Corrections {suffix}", short_name=f"OC_{suffix}")
            session.add(org)
            await session.flush()

        unit = Unit(organization_id=org.id, name=f"Unit {suffix}", code=f"UC_{suffix}")
        other_unit = Unit(organization_id=org.id, name=f"Other Unit {suffix}", code=f"UO_{suffix}")
        session.add_all([unit, other_unit])
        await session.flush()

        dept = Department(unit_id=unit.id, name=f"Dept {suffix}", code=f"DC_{suffix}")
        session.add(dept)
        await session.flush()

        async def make_user(label: str) -> User:
            user = User(
                email=f"{label}.{suffix}@corrections.test",
                username=f"{label}.{suffix}",
                first_name=label.title(),
                last_name="Tester",
                hashed_password="not-used-by-token-tests",
                is_active=True,
                is_verified=True,
            )
            session.add(user)
            await session.flush()
            return user

        hr_user = await make_user("hr")
        org_hr_user = await make_user("orghr")
        member_user = await make_user("member")
        outsider_user = await make_user("outsider")

        hr_employee = Employee(
            user_id=hr_user.id,
            employee_code=f"HR_{suffix}",
            first_name="Hr",
            last_name="Admin",
            role="HR_ADMIN",
            business_role="HR_ADMIN",
            access_scope="UNIT",
            unit_id=unit.id,
            department_id=dept.id,
            status="ACTIVE",
        )
        # Same HR role, organization scope and no unit: organization-level HR.
        org_hr_employee = Employee(
            user_id=org_hr_user.id,
            employee_code=f"OHR_{suffix}",
            first_name="Org",
            last_name="Hr",
            role="HR_ADMIN",
            business_role="HR_ADMIN",
            access_scope="ORGANIZATION",
            status="ACTIVE",
        )
        member_employee = Employee(
            user_id=member_user.id,
            employee_code=f"MB_{suffix}",
            first_name="Member",
            last_name="One",
            role="EMPLOYEE",
            unit_id=unit.id,
            department_id=dept.id,
            status="ACTIVE",
        )
        outsider_employee = Employee(
            user_id=outsider_user.id,
            employee_code=f"OU_{suffix}",
            first_name="Outsider",
            last_name="Two",
            role="EMPLOYEE",
            unit_id=other_unit.id,
            status="ACTIVE",
        )
        session.add_all([hr_employee, org_hr_employee, member_employee, outsider_employee])
        await session.flush()

        record = AttendanceRecord(employee_id=member_employee.id, attendance_date="2026-03-02", status="MISSED_PUNCH")
        # A second record without a pending correction, for the submission test.
        free_record = AttendanceRecord(employee_id=member_employee.id, attendance_date="2026-03-03", status="MISSED_PUNCH")
        # The other unit needs its own correction and free record, so a scoped
        # caller can be shown to reach exactly one of the two units.
        other_record = AttendanceRecord(employee_id=outsider_employee.id, attendance_date="2026-03-02", status="MISSED_PUNCH")
        other_free_record = AttendanceRecord(employee_id=outsider_employee.id, attendance_date="2026-03-03", status="MISSED_PUNCH")
        session.add_all([record, free_record, other_record, other_free_record])
        await session.flush()

        correction = AttendanceCorrectionRequest(
            attendance_record_id=record.id,
            requested_punch_in="09:15",
            requested_punch_out="18:05",
            reason=f"Forgot to punch out {suffix}",
            status="PENDING",
        )
        session.add(correction)
        other_correction = AttendanceCorrectionRequest(
            attendance_record_id=other_record.id,
            requested_punch_in="09:20",
            requested_punch_out="18:00",
            reason=f"Forgot to punch in {suffix}",
            status="PENDING",
        )
        session.add(other_correction)
        await session.flush()

        strategy = get_jwt_strategy()
        tokens = {
            "hr": await strategy.write_token(hr_user),
            "org_hr": await strategy.write_token(org_hr_user),
            "member": await strategy.write_token(member_user),
            "outsider": await strategy.write_token(outsider_user),
        }
        correction_id = correction.id
        other_correction_id = other_correction.id
        record_id = record.id
        free_record_id = free_record.id
        other_free_record_id = other_free_record.id
        await session.commit()

    # The app runs in the TestClient's own event loop; release pooled
    # connections here so it opens fresh ones on its loop.
    await auth_engine.dispose()
    return {
        **tokens,
        "correction_id": correction_id,
        "other_correction_id": other_correction_id,
        "record_id": record_id,
        "free_record_id": free_record_id,
        "other_free_record_id": other_free_record_id,
    }


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_hr_lists_unit_corrections_and_employees_see_only_their_own(unique_suffix):
    seeded = run_async(_seed(unique_suffix))
    correction_id = seeded["correction_id"]

    with TestClient(app) as client:
        hr_response = client.get("/api/v1/attendance/corrections", headers=_auth(str(seeded["hr"])))
        assert hr_response.status_code == 200, hr_response.text
        assert correction_id in [item["id"] for item in hr_response.json()["items"]]

        member_response = client.get("/api/v1/attendance/corrections", headers=_auth(str(seeded["member"])))
        assert member_response.status_code == 200, member_response.text
        assert correction_id in [item["id"] for item in member_response.json()["items"]]

        outsider_response = client.get("/api/v1/attendance/corrections", headers=_auth(str(seeded["outsider"])))
        assert outsider_response.status_code == 200, outsider_response.text
        assert correction_id not in [item["id"] for item in outsider_response.json()["items"]]


def test_unit_hr_is_confined_to_their_unit_while_organization_hr_covers_every_unit(unique_suffix):
    """Same HR role, same permissions — only the access scope differs."""
    seeded = run_async(_seed(unique_suffix))
    in_unit_id = seeded["correction_id"]
    out_of_unit_id = seeded["other_correction_id"]

    with TestClient(app) as client:
        unit_hr_listing = client.get("/api/v1/attendance/corrections", headers=_auth(str(seeded["hr"])))
        assert unit_hr_listing.status_code == 200, unit_hr_listing.text
        assert {item["id"] for item in unit_hr_listing.json()["items"]} == {in_unit_id}

        org_hr_listing = client.get("/api/v1/attendance/corrections", headers=_auth(str(seeded["org_hr"])))
        assert org_hr_listing.status_code == 200, org_hr_listing.text
        assert {item["id"] for item in org_hr_listing.json()["items"]} >= {in_unit_id, out_of_unit_id}

        outside_payload = {
            "attendance_record_id": seeded["other_free_record_id"],
            "requested_punch_in": "09:10",
            "requested_punch_out": "18:05",
            "reason": "Out-of-unit correction attempt",
        }
        unit_hr_attempt = client.post(
            "/api/v1/attendance/corrections",
            json=outside_payload,
            headers=_auth(str(seeded["hr"])),
        )
        assert unit_hr_attempt.status_code == 403, unit_hr_attempt.text

        org_hr_attempt = client.post(
            "/api/v1/attendance/corrections",
            json=outside_payload,
            headers=_auth(str(seeded["org_hr"])),
        )
        assert org_hr_attempt.status_code == 201, org_hr_attempt.text


def test_raising_a_correction_is_hr_only(unique_suffix):
    """The attendance UI hides the action for everyone else because the API refuses them."""
    seeded = run_async(_seed(unique_suffix))
    payload = {
        "attendance_record_id": seeded["free_record_id"],
        "requested_punch_in": "09:05",
        "requested_punch_out": "18:10",
        "reason": "Punch device was offline",
    }

    with TestClient(app) as client:
        employee_attempt = client.post(
            "/api/v1/attendance/corrections",
            json=payload,
            headers=_auth(str(seeded["member"])),
        )
        assert employee_attempt.status_code == 403, employee_attempt.text

        hr_attempt = client.post(
            "/api/v1/attendance/corrections",
            json={**payload, "reason": "Punch device was offline (HR verified)"},
            headers=_auth(str(seeded["hr"])),
        )
        assert hr_attempt.status_code == 201, hr_attempt.text
        assert hr_attempt.json()["status"] == "PENDING"
        assert hr_attempt.json()["sync_status"] == "PENDING_ERP_RECONCILIATION"


def test_correction_approval_endpoints_are_removed(unique_suffix):
    """ERP confirms corrections, so HRMS must not expose an approval action."""
    seeded = run_async(_seed(unique_suffix))
    correction_id = seeded["correction_id"]
    headers = _auth(str(seeded["hr"]))

    with TestClient(app) as client:
        approve = client.patch(f"/api/v1/attendance/corrections/{correction_id}/approve", headers=headers)
        reject = client.patch(f"/api/v1/attendance/corrections/{correction_id}/reject", headers=headers)
        # No route serves these paths at all (404), and never a wrong-method 405.
        assert approve.status_code in {404, 405}, approve.text
        assert reject.status_code in {404, 405}, reject.text

    paths = app.openapi()["paths"]
    assert "/api/v1/attendance/corrections/{correction_id}/approve" not in paths
    assert "/api/v1/attendance/corrections/{correction_id}/reject" not in paths
