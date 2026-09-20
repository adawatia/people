import asyncio
import selectors
import sys
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi import HTTPException

from core.database import async_session_maker
from db.models import Department, Designation, Employee, LeaveApplication, LeaveType, Organization, Unit, User
from schemas.attendance import (
    AttendanceCorrectionCreate,
    AttendancePunchCreate,
    ProcessAttendanceRequest,
)
from schemas.holidays import HolidayListCreate
from schemas.shifts import ShiftAssignmentCreate, ShiftCreate
from services.attendance_service import AttendanceService
from services.holiday_service import HolidayService
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


async def _setup_m3_test_environment(session, suffix: str):
    org = Organization(name=f"Org M3 {suffix}", short_name=f"O3_{suffix}")
    session.add(org)
    await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit M3 {suffix}", code=f"U3_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Dept M3 {suffix}", code=f"D3_{suffix}")
    session.add(dept)
    await session.flush()

    desig = Designation(name=f"Engineer M3 {suffix}", code=f"E3_{suffix}")
    session.add(desig)
    await session.flush()

    emp = Employee(
        first_name="Amit",
        last_name="Verma",
        employee_code=f"EMP_M3_{suffix}",
        official_email=f"amit_{suffix}@example.com",
        unit_id=unit.id,
        department_id=dept.id,
        designation_id=desig.id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(emp)
    await session.flush()

    # Create Shift: 09:00 - 18:00 (break 30 min, late_grace 10 min, early_grace 10 min, half_day 4.0h, absent 2.0h)
    shift_service = ShiftService(session)
    shift = await shift_service.create_shift(
        ShiftCreate(
            name=f"Shift M3 {suffix}",
            code=f"S3_{suffix}",
            start_time=time(9, 0),
            end_time=time(18, 0),
            break_minutes=30,
            late_entry_grace_minutes=10,
            early_exit_grace_minutes=10,
            half_day_threshold_hours=4.0,
            absent_threshold_hours=2.0,
            begin_check_in_before_minutes=60,
            allow_check_out_after_minutes=60,
        )
    )

    # Assign shift for August 2026
    await shift_service.assign_shift(
        ShiftAssignmentCreate(
            employee_id=emp.id,
            shift_id=shift.id,
            effective_from=date(2026, 8, 1),
            effective_to=date(2026, 8, 31),
        )
    )

    # Create Holiday List with Sunday weekly offs
    holiday_service = HolidayService(session)
    await holiday_service.create_holiday_list(
        HolidayListCreate(
            name=f"Holiday List M3 {suffix}",
            unit_id=unit.id,
            from_date=date(2026, 8, 1),
            to_date=date(2026, 8, 31),
            weekly_off_day="Sunday",
            is_default=True,
        ),
        auto_generate_weekly_offs=True,
    )

    await session.commit()
    return org, unit, dept, desig, emp, shift


def test_attendance_processing_present_full_day(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, shift = await _setup_m3_test_environment(session, unique_suffix)
            att_service = AttendanceService(session)

            target_date = date(2026, 8, 3)  # Monday

            # Ingest IN punch: 08:55 (within buffer, not late)
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 3, 8, 55, 0),
                    punch_type="IN",
                    source="BIOMETRIC",
                )
            )
            # Ingest OUT punch: 18:05 (completed shift, not early exit)
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 3, 18, 5, 0),
                    punch_type="OUT",
                    source="BIOMETRIC",
                )
            )

            # Process Attendance
            rec, is_created = await att_service.process_attendance_for_employee_date(emp, target_date)
            await session.commit()

            assert is_created is True
            assert rec.status == "PRESENT"
            assert rec.punch_in == time(8, 55)
            assert rec.punch_out == time(18, 5)
            # 550 min gross - 30 min break = 520 min worked
            assert rec.worked_minutes == 520
            assert rec.late_minutes == 0
            assert rec.early_exit_minutes == 0

            # Verify punches are marked processed
            punches = await att_service.list_punches(employee_id=emp.id, is_processed=True)
            assert len(punches) == 2
            assert all(p.attendance_record_id == rec.id for p in punches)

    run_async(_test())


def test_attendance_processing_late_and_early_exit(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, shift = await _setup_m3_test_environment(session, unique_suffix)
            att_service = AttendanceService(session)

            target_date = date(2026, 8, 4)  # Tuesday

            # Punch IN at 09:25 (shift start 09:00, late_grace 10 min -> 25 min late)
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 4, 9, 25, 0),
                    punch_type="IN",
                )
            )
            # Punch OUT at 17:35 (shift end 18:00, early_grace 10 min -> 25 min early exit)
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 4, 17, 35, 0),
                    punch_type="OUT",
                )
            )

            rec, _ = await att_service.process_attendance_for_employee_date(emp, target_date)
            await session.commit()

            assert rec.status == "PRESENT"
            assert rec.late_minutes == 25
            assert rec.early_exit_minutes == 25

    run_async(_test())


def test_attendance_thresholds_half_day_and_absent(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, shift = await _setup_m3_test_environment(session, unique_suffix)
            att_service = AttendanceService(session)

            # 1. Half Day: Worked 3.5 hours (210 min gross - 30 min break = 180 min net = 3.0 hrs, which is < 4.0h threshold)
            date_half = date(2026, 8, 5)
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 5, 9, 0, 0),
                    punch_type="IN",
                )
            )
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 5, 12, 30, 0),
                    punch_type="OUT",
                )
            )
            rec_half, _ = await att_service.process_attendance_for_employee_date(emp, date_half)
            assert rec_half.status == "HALF_DAY"

            # 2. Absent due to under-threshold: Worked 1.5 hours (< 2.0h absent threshold)
            date_absent = date(2026, 8, 6)
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 6, 9, 0, 0),
                    punch_type="IN",
                )
            )
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 6, 10, 30, 0),
                    punch_type="OUT",
                )
            )
            rec_abs, _ = await att_service.process_attendance_for_employee_date(emp, date_absent)
            assert rec_abs.status == "ABSENT"

    run_async(_test())


def test_attendance_missed_punch(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, shift = await _setup_m3_test_environment(session, unique_suffix)
            att_service = AttendanceService(session)

            target_date = date(2026, 8, 7)

            # Only IN punch, forgot OUT punch
            await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=datetime(2026, 8, 7, 9, 0, 0),
                    punch_type="IN",
                )
            )

            rec, _ = await att_service.process_attendance_for_employee_date(emp, target_date)
            assert rec.status == "MISSED_PUNCH"
            assert rec.punch_in == time(9, 0)
            assert rec.punch_out is None
            assert rec.worked_minutes == 0

    run_async(_test())


def test_unpunched_days_weekly_off_leave_and_absent(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, _ = await _setup_m3_test_environment(session, unique_suffix)
            att_service = AttendanceService(session)

            # 1. Sunday (August 2, 2026) -> WEEKLY_OFF
            sunday = date(2026, 8, 2)
            rec_sun, _ = await att_service.process_attendance_for_employee_date(emp, sunday)
            assert rec_sun.status == "WEEKLY_OFF"

            # 2. Approved Leave on Monday August 10, 2026 -> ON_LEAVE
            leave_date = date(2026, 8, 10)
            lt = LeaveType(name=f"Casual Leave {unique_suffix}", code=f"CL_{unique_suffix}", annual_allocation=12)
            session.add(lt)
            await session.flush()

            leave_app = LeaveApplication(
                employee_id=emp.id,
                leave_type_id=lt.id,
                from_date=leave_date,
                to_date=leave_date,
                days_count=1,
                status="APPROVED",
            )
            session.add(leave_app)
            await session.commit()

            rec_leave, _ = await att_service.process_attendance_for_employee_date(emp, leave_date)
            assert rec_leave.status == "ON_LEAVE"

            # 3. Regular working Wednesday August 12, 2026 with no punches -> ABSENT
            workday = date(2026, 8, 12)
            rec_abs, _ = await att_service.process_attendance_for_employee_date(emp, workday)
            assert rec_abs.status == "ABSENT"

    run_async(_test())


def test_attendance_correction_regularization_workflow(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, _ = await _setup_m3_test_environment(session, unique_suffix)
            att_service = AttendanceService(session)

            # Process an unpunched day to ABSENT
            target_date = date(2026, 8, 14)
            rec, _ = await att_service.process_attendance_for_employee_date(emp, target_date)
            await session.commit()
            assert rec.status == "ABSENT"

            # 1. Employee submits correction request
            corr = await att_service.submit_correction(
                AttendanceCorrectionCreate(
                    attendance_record_id=rec.id,
                    requested_punch_in="09:00",
                    requested_punch_out="18:00",
                    reason="Biometric device was down for maintenance at Unit gate",
                )
            )
            assert corr.id is not None
            assert corr.status == "PENDING"
            assert corr.requested_punch_in == time(9, 0)
            assert corr.requested_punch_out == time(18, 0)

            # 2. Manager approves correction
            fake_user = User(
                username=f"hr_mgr_{unique_suffix}",
                email=f"hr_mgr_{unique_suffix}@example.com",
                hashed_password="fake",
                first_name="HR",
                last_name="Manager",
            )
            session.add(fake_user)
            await session.flush()

            res = await att_service.approve_correction(corr.id, fake_user.id)
            assert res["status"] == "approved"

            # 3. Verify AttendanceRecord updated to PRESENT with proper times and worked minutes
            refreshed_rec = await att_service.record_repo.get_by_id(rec.id)
            assert refreshed_rec.status == "PRESENT"
            assert refreshed_rec.punch_in == time(9, 0)
            assert refreshed_rec.punch_out == time(18, 0)
            assert refreshed_rec.worked_minutes == 540

    run_async(_test())
