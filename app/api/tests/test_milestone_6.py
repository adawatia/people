import asyncio
import selectors
import sys
import uuid
from datetime import date, datetime, time

import pytest

from core.database import async_session_maker
from db.models import Department, Designation, Employee, Organization, Unit
from schemas.attendance import AttendancePunchCreate
from schemas.holidays import HolidayListCreate
from schemas.leaves import LeaveAllocationCreate, LeavePeriodCreate, LeaveTypeCreate
from schemas.shifts import ShiftAssignmentCreate, ShiftCreate
from services.attendance_service import AttendanceService
from services.holiday_service import HolidayService
from services.leave_service import LeaveService
from services.report_service import ReportService
from services.shift_service import ShiftService


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


async def _setup_m6_test_environment(session, suffix: str):
    org = Organization(name=f"Org M6 {suffix}", short_name=f"O6_{suffix}")
    session.add(org)
    await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit M6 {suffix}", code=f"U6_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Dept M6 {suffix}", code=f"D6_{suffix}")
    session.add(dept)
    await session.flush()

    desig = Designation(name=f"Engineer M6 {suffix}", code=f"E6_{suffix}")
    session.add(desig)
    await session.flush()

    emp = Employee(
        first_name="Vikas",
        last_name="Patil",
        employee_code=f"EMP_M6_{suffix}",
        official_email=f"vikas_{suffix}@example.com",
        unit_id=unit.id,
        department_id=dept.id,
        designation_id=desig.id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(emp)
    await session.flush()

    # Shift
    shift_service = ShiftService(session)
    shift = await shift_service.create_shift(
        ShiftCreate(
            name=f"General M6 {suffix}",
            code=f"GEN_M6_{suffix}",
            start_time=time(9, 0),
            end_time=time(18, 0),
            break_minutes=30,
        )
    )
    await shift_service.assign_shift(
        ShiftAssignmentCreate(
            employee_id=emp.id,
            shift_id=shift.id,
            effective_from=date(2026, 10, 1),
            effective_to=date(2026, 10, 31),
        )
    )

    # Holidays (Sundays)
    holiday_service = HolidayService(session)
    await holiday_service.create_holiday_list(
        HolidayListCreate(
            name=f"Holiday List M6 {suffix}",
            unit_id=unit.id,
            from_date=date(2026, 10, 1),
            to_date=date(2026, 10, 31),
            weekly_off_day="Sunday",
            is_default=True,
        ),
        auto_generate_weekly_offs=True,
    )

    await session.commit()
    return org, unit, dept, desig, emp, shift


def test_monthly_attendance_matrix_report(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, unit, dept, _, emp, shift = await _setup_m6_test_environment(session, unique_suffix)
            att_service = AttendanceService(session)
            report_service = ReportService(session)

            # Oct 1, 2026 is Thursday -> Record full day punches
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 10, 1, 8, 58, 0),
                    punch_type="IN",
                )
            )
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 10, 1, 18, 2, 0),
                    punch_type="OUT",
                )
            )
            await att_service.process_attendance_for_employee_date(emp, date(2026, 10, 1))

            # Oct 4, 2026 is Sunday -> Weekly off
            await att_service.process_attendance_for_employee_date(emp, date(2026, 10, 4))

            # Oct 5, 2026 is Monday -> Unpunched absent
            await att_service.process_attendance_for_employee_date(emp, date(2026, 10, 5))

            await session.commit()

            # Generate Report
            matrix = await report_service.get_monthly_attendance_matrix(
                year=2026,
                month=10,
                unit_id=unit.id,
            )

            assert matrix.total_days_in_month == 31
            assert len(matrix.rows) >= 1
            emp_row = next(r for r in matrix.rows if r.employee_id == emp.id)
            assert emp_row.employee_code == emp.employee_code
            assert emp_row.department_name == dept.name

            # Check day status mapping
            assert emp_row.day_status_map[1] == "P"   # Day 1: Present
            assert emp_row.day_status_map[4] == "WO"  # Day 4: Weekly Off
            assert emp_row.day_status_map[5] == "A"   # Day 5: Absent
            assert emp_row.day_status_map[10] == "-"  # Unprocessed day

            assert emp_row.total_present == 1
            assert emp_row.total_weekly_off == 1
            assert emp_row.total_absent == 1

    run_async(_test())


def test_leave_balance_summary_report(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, unit, dept, _, emp, _ = await _setup_m6_test_environment(session, unique_suffix)
            leave_service = LeaveService(session)
            report_service = ReportService(session)

            period = await leave_service.create_period(
                LeavePeriodCreate(
                    name=f"Period 2026 {unique_suffix}",
                    from_date=date(2026, 1, 1),
                    to_date=date(2026, 12, 31),
                )
            )
            lt = await leave_service.create_type(
                LeaveTypeCreate(
                    name=f"Sick Leave {unique_suffix}",
                    code=f"SL_M6_{unique_suffix}",
                    annual_allocation=10,
                )
            )
            await leave_service.allocate_leaves(
                LeaveAllocationCreate(
                    employee_id=emp.id,
                    leave_type_id=lt.id,
                    leave_period_id=period.id,
                    new_leaves_allocated=10.0,
                )
            )

            report = await report_service.get_leave_balance_summary(
                year=2026,
                unit_id=unit.id,
            )
            assert len(report.rows) >= 1
            row = next(r for r in report.rows if r.employee_id == emp.id and r.leave_type_id == lt.id) if hasattr(report.rows[0], 'leave_type_id') else next(r for r in report.rows if r.employee_id == emp.id and r.leave_type_code == lt.code)
            assert row.allocated == 10.0
            assert row.available == 10.0

    run_async(_test())
