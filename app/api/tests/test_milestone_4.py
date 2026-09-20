import asyncio
import selectors
import sys
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi import HTTPException

from core.database import async_session_maker
from db.models import Department, Designation, Employee, Organization, Unit, User
from schemas.holidays import HolidayListCreate
from schemas.leaves import (
    LeaveAllocationCreate,
    LeaveApplicationCreate,
    LeavePeriodCreate,
    LeaveTypeCreate,
)
from services.holiday_service import HolidayService
from services.leave_service import LeaveService


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


async def _setup_m4_test_environment(session, suffix: str):
    org = Organization(name=f"Org M4 {suffix}", short_name=f"O4_{suffix}")
    session.add(org)
    await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit M4 {suffix}", code=f"U4_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Dept M4 {suffix}", code=f"D4_{suffix}")
    session.add(dept)
    await session.flush()

    desig = Designation(name=f"Engineer M4 {suffix}", code=f"E4_{suffix}")
    session.add(desig)
    await session.flush()

    emp = Employee(
        first_name="Rohan",
        last_name="Mehta",
        employee_code=f"EMP_M4_{suffix}",
        official_email=f"rohan_{suffix}@example.com",
        unit_id=unit.id,
        department_id=dept.id,
        designation_id=desig.id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(emp)
    await session.flush()

    # Create Holiday List with Sunday weekly offs
    holiday_service = HolidayService(session)
    await holiday_service.create_holiday_list(
        HolidayListCreate(
            name=f"Holiday List M4 {suffix}",
            unit_id=unit.id,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 12, 31),
            weekly_off_day="Sunday",
            is_default=True,
        ),
        auto_generate_weekly_offs=True,
    )

    # Create Leave Period for 2026
    leave_service = LeaveService(session)
    period = await leave_service.create_period(
        LeavePeriodCreate(
            name=f"Calendar Year 2026 {suffix}",
            from_date=date(2026, 1, 1),
            to_date=date(2026, 12, 31),
            is_active=True,
        )
    )

    await session.commit()
    return org, unit, dept, desig, emp, period


def test_leave_period_and_type_creation(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, period = await _setup_m4_test_environment(session, unique_suffix)
            service = LeaveService(session)

            # 1. Create Casual Leave (does not include holidays)
            cl = await service.create_type(
                LeaveTypeCreate(
                    name=f"Casual Leave {unique_suffix}",
                    code=f"CL_{unique_suffix}",
                    is_paid=True,
                    annual_allocation=12,
                    include_holidays=False,
                )
            )
            assert cl.id is not None
            assert cl.include_holidays is False

            # 2. Duplicate code rejected
            with pytest.raises(HTTPException) as exc:
                await service.create_type(
                    LeaveTypeCreate(
                        name=f"Another CL {unique_suffix}",
                        code=f"CL_{unique_suffix}",
                    )
                )
            assert exc.value.status_code == 400

    run_async(_test())


def test_leave_allocation_and_ledger_credit(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, period = await _setup_m4_test_environment(session, unique_suffix)
            service = LeaveService(session)

            cl = await service.create_type(
                LeaveTypeCreate(
                    name=f"Paid Leave {unique_suffix}",
                    code=f"PL_{unique_suffix}",
                    is_paid=True,
                    annual_allocation=18,
                )
            )

            # Allocate 18 days
            alloc = await service.allocate_leaves(
                LeaveAllocationCreate(
                    employee_id=emp.id,
                    leave_type_id=cl.id,
                    leave_period_id=period.id,
                    new_leaves_allocated=18.0,
                    carry_forwarded_leaves=2.0,
                )
            )
            assert alloc.id is not None
            assert alloc.total_leaves_allocated == 20.0

            # Verify balance
            balances = await service.get_employee_leave_balances(emp.id)
            pl_balance = next(b for b in balances if b.leave_type_id == cl.id)
            assert pl_balance.available == 20.0
            assert pl_balance.used == 0.0

    run_async(_test())


def test_effective_leave_days_excluding_holidays(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, period = await _setup_m4_test_environment(session, unique_suffix)
            service = LeaveService(session)

            cl = await service.create_type(
                LeaveTypeCreate(
                    name=f"Privilege Leave {unique_suffix}",
                    code=f"PRL_{unique_suffix}",
                    include_holidays=False,
                )
            )
            ml = await service.create_type(
                LeaveTypeCreate(
                    name=f"Maternity Leave {unique_suffix}",
                    code=f"MAT_{unique_suffix}",
                    include_holidays=True,
                )
            )

            # Aug 7, 2026 is Friday, Aug 8 is Saturday, Aug 9 is Sunday (Weekly Off), Aug 10 is Monday.
            # Range: Aug 7 to Aug 10 (4 calendar days)
            from_d = date(2026, 8, 7)
            to_d = date(2026, 8, 10)

            # PRL excludes Sunday weekly-off -> 3 effective days (or 2 if Saturday was also off, here Sunday is weekly off)
            days_prl = await service.calculate_leave_days(emp.id, cl, from_d, to_d)
            assert days_prl == 3.0  # Sunday excluded

            # MAT includes holidays -> 4 effective days
            days_mat = await service.calculate_leave_days(emp.id, ml, from_d, to_d)
            assert days_mat == 4.0

    run_async(_test())


def test_insufficient_leave_balance_prevention(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, period = await _setup_m4_test_environment(session, unique_suffix)
            service = LeaveService(session)

            cl = await service.create_type(
                LeaveTypeCreate(
                    name=f"Short Leave {unique_suffix}",
                    code=f"SL_{unique_suffix}",
                )
            )
            # Allocate only 2 days
            await service.allocate_leaves(
                LeaveAllocationCreate(
                    employee_id=emp.id,
                    leave_type_id=cl.id,
                    leave_period_id=period.id,
                    new_leaves_allocated=2.0,
                )
            )

            # Request 5 days (Monday to Friday, Aug 17 to Aug 21)
            with pytest.raises(HTTPException) as exc:
                await service.apply_leave(
                    LeaveApplicationCreate(
                        employee_id=emp.id,
                        leave_type_id=cl.id,
                        from_date=date(2026, 8, 17),
                        to_date=date(2026, 8, 21),
                    )
                )
            assert exc.value.status_code == 400
            assert "Insufficient leave balance" in exc.value.detail

    run_async(_test())


def test_leave_approval_ledger_debit_and_attendance_marking(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, period = await _setup_m4_test_environment(session, unique_suffix)
            service = LeaveService(session)

            cl = await service.create_type(
                LeaveTypeCreate(
                    name=f"Earned Leave {unique_suffix}",
                    code=f"EL_{unique_suffix}",
                    annual_allocation=15,
                )
            )
            await service.allocate_leaves(
                LeaveAllocationCreate(
                    employee_id=emp.id,
                    leave_type_id=cl.id,
                    leave_period_id=period.id,
                    new_leaves_allocated=15.0,
                )
            )

            # Apply for 2 days (Aug 17 Monday to Aug 18 Tuesday)
            app = await service.apply_leave(
                LeaveApplicationCreate(
                    employee_id=emp.id,
                    leave_type_id=cl.id,
                    from_date=date(2026, 8, 17),
                    to_date=date(2026, 8, 18),
                    reason="Family event",
                )
            )
            assert app.id is not None
            assert app.status == "PENDING"
            assert app.days_count == 2.0

            # Manager User
            manager = User(
                username=f"mgr_{unique_suffix}",
                email=f"mgr_{unique_suffix}@example.com",
                hashed_password="fake",
                first_name="Manager",
                last_name="One",
            )
            session.add(manager)
            await session.flush()

            # Approve leave
            approved = await service.approve_leave(app.id, manager.id)
            assert approved.status == "APPROVED"

            # Check ledger: 15.0 allocation + (-2.0) application = 13.0 balance
            balances = await service.get_employee_leave_balances(emp.id)
            b = next(b for b in balances if b.leave_type_id == cl.id)
            assert b.available == 13.0
            assert b.used == 2.0

            # Check AttendanceRecord updated to ON_LEAVE for Aug 17 & Aug 18
            rec1 = await service.attendance_record_repo.get_by_employee_and_date(emp.id, date(2026, 8, 17))
            rec2 = await service.attendance_record_repo.get_by_employee_and_date(emp.id, date(2026, 8, 18))
            assert rec1 is not None and rec1.status == "ON_LEAVE"
            assert rec2 is not None and rec2.status == "ON_LEAVE"

            # 4. Cancel leave and check reversal
            cancelled = await service.cancel_leave(app.id, manager.id)
            assert cancelled.status == "CANCELLED"

            balances_after = await service.get_employee_leave_balances(emp.id)
            b_after = next(b for b in balances_after if b.leave_type_id == cl.id)
            assert b_after.available == 15.0

    run_async(_test())
