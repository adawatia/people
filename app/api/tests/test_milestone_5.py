import asyncio
import selectors
import sys
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from core.database import async_session_maker
from db.models import Department, Designation, Employee, Organization, Unit, User
from schemas.work_arrangements import WorkArrangementCreate
from services.work_arrangement_service import WorkArrangementService


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


async def _setup_m5_test_environment(session, suffix: str):
    org = await session.scalar(select(Organization).order_by(Organization.id.asc()))
    if org is None:
        org = Organization(name=f"Org M5 {suffix}", short_name=f"O5_{suffix}")
        session.add(org)
        await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit M5 {suffix}", code=f"U5_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Dept M5 {suffix}", code=f"D5_{suffix}")
    session.add(dept)
    await session.flush()

    desig = Designation(name=f"Engineer M5 {suffix}", code=f"E5_{suffix}")
    session.add(desig)
    await session.flush()

    emp = Employee(
        first_name="Neha",
        last_name="Gupta",
        employee_code=f"EMP_M5_{suffix}",
        official_email=f"neha_{suffix}@example.com",
        unit_id=unit.id,
        department_id=dept.id,
        designation_id=desig.id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(emp)

    manager = User(
        username=f"mgr_m5_{suffix}",
        email=f"mgr_m5_{suffix}@example.com",
        hashed_password="fake",
        first_name="Manager",
        last_name="Five",
    )
    session.add(manager)
    await session.commit()
    return org, unit, dept, desig, emp, manager


def test_work_arrangement_creation_and_overlap_prevention(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, manager = await _setup_m5_test_environment(session, unique_suffix)
            service = WorkArrangementService(session)

            # 1. Create WFH request
            req1 = await service.create_request(
                WorkArrangementCreate(
                    employee_id=emp.id,
                    arrangement_type="WORK_FROM_HOME",
                    from_date=date(2026, 9, 1),
                    to_date=date(2026, 9, 5),
                    reason="Home renovation and remote dev work",
                )
            )
            assert req1.id is not None
            assert req1.status == "PENDING"
            assert req1.arrangement_type == "WORK_FROM_HOME"

            # 2. Overlap attempt fails
            with pytest.raises(HTTPException) as exc:
                await service.create_request(
                    WorkArrangementCreate(
                        employee_id=emp.id,
                        arrangement_type="WORK_FROM_HOME",
                        from_date=date(2026, 9, 3),
                        to_date=date(2026, 9, 7),
                        reason="Client site visit",
                    )
                )
            assert exc.value.status_code == 400
            assert "already has an active work arrangement" in exc.value.detail

    run_async(_test())


def test_work_arrangement_approval_and_wfh_attendance_marking(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, manager = await _setup_m5_test_environment(session, unique_suffix)
            service = WorkArrangementService(session)

            target_date = date(2026, 9, 10)
            req = await service.create_request(
                WorkArrangementCreate(
                    employee_id=emp.id,
                    arrangement_type="WORK_FROM_HOME",
                    from_date=target_date,
                    to_date=target_date,
                    reason="Doctor appointment nearby home",
                )
            )

            # Manager approves
            approved = await service.approve_request(req.id, manager.id)
            assert approved.status == "APPROVED"

            # Verify AttendanceRecord created with status WORK_FROM_HOME
            rec = await service.attendance_record_repo.get_by_employee_and_date(emp.id, target_date)
            assert rec is not None
            assert rec.status == "WORK_FROM_HOME"

    run_async(_test())


def test_work_arrangement_rejection_and_cancellation(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, manager = await _setup_m5_test_environment(session, unique_suffix)
            service = WorkArrangementService(session)

            # 1. Rejection
            req1 = await service.create_request(
                WorkArrangementCreate(
                    employee_id=emp.id,
                    arrangement_type="WORK_FROM_HOME",
                    from_date=date(2026, 9, 20),
                    to_date=date(2026, 9, 21),
                    reason="Personal",
                )
            )
            rej = await service.reject_request(req1.id, manager.id, rejection_reason="Critical machinery rollout on floor")
            assert rej.status == "REJECTED"
            assert rej.rejection_reason == "Critical machinery rollout on floor"

            # 2. Cancellation by employee
            req2 = await service.create_request(
                WorkArrangementCreate(
                    employee_id=emp.id,
                    arrangement_type="WORK_FROM_HOME",
                    from_date=date(2026, 9, 25),
                    to_date=date(2026, 9, 25),
                    reason="Vendor survey",
                )
            )
            canc = await service.cancel_request(req2.id, manager.id)
            assert canc.status == "CANCELLED"

    run_async(_test())
