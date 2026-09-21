import asyncio
import selectors
import sys
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from core.database import async_session_maker
from db.models import Department, Designation, Employee, Organization, Shift, Unit
from schemas.attendance import AttendancePunchCreate, BulkPunchCreate
from schemas.holidays import HolidayCreate, HolidayListCreate
from schemas.shifts import BulkShiftAssignmentCreate, ShiftAssignmentCreate, ShiftCreate
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


async def _get_or_create_org_structure(session, suffix: str):
    org = await session.scalar(select(Organization).order_by(Organization.id.asc()))
    if org is None:
        org = Organization(name=f"Org M2 {suffix}", short_name=f"O_{suffix}")
        session.add(org)
        await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit M2 {suffix}", code=f"UM2_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Dept M2 {suffix}", code=f"DM2_{suffix}")
    session.add(dept)
    await session.flush()

    desig = Designation(name=f"Eng M2 {suffix}", code=f"EM2_{suffix}")
    session.add(desig)
    await session.flush()

    emp = Employee(
        first_name="Priya",
        last_name="Sharma",
        employee_code=f"EMP_M2_{suffix}",
        official_email=f"priya_{suffix}@example.com",
        department_id=dept.id,
        designation_id=desig.id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(emp)
    await session.flush()
    await session.commit()
    return org, unit, dept, desig, emp


def test_shift_creation_and_night_shift_flag(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            service = ShiftService(session)

            # 1. Day Shift (09:00 - 18:00)
            day_shift = await service.create_shift(
                ShiftCreate(
                    name=f"General Day {unique_suffix}",
                    code=f"DAY_{unique_suffix}",
                    start_time=time(9, 0),
                    end_time=time(18, 0),
                    begin_check_in_before_minutes=60,
                    allow_check_out_after_minutes=60,
                )
            )
            assert day_shift.id is not None
            assert day_shift.is_cross_midnight is False

            # 2. Night Shift (22:00 - 06:00)
            night_shift = await service.create_shift(
                ShiftCreate(
                    name=f"Night Shift {unique_suffix}",
                    code=f"NIGHT_{unique_suffix}",
                    start_time=time(22, 0),
                    end_time=time(6, 0),
                    begin_check_in_before_minutes=60,
                    allow_check_out_after_minutes=60,
                )
            )
            assert night_shift.id is not None
            assert night_shift.is_cross_midnight is True

            # 3. Validation: Start and end identical
            with pytest.raises(HTTPException) as exc:
                await service.create_shift(
                    ShiftCreate(
                        name=f"Invalid Shift {unique_suffix}",
                        code=f"INV_{unique_suffix}",
                        start_time=time(10, 0),
                        end_time=time(10, 0),
                    )
                )
            assert exc.value.status_code == 400

    run_async(_test())


def test_shift_assignment_overlap_prevention(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp = await _get_or_create_org_structure(session, unique_suffix)
            service = ShiftService(session)

            s1 = await service.create_shift(
                ShiftCreate(
                    name=f"Morning {unique_suffix}",
                    code=f"MOR_{unique_suffix}",
                    start_time=time(6, 0),
                    end_time=time(14, 0),
                )
            )
            s2 = await service.create_shift(
                ShiftCreate(
                    name=f"Evening {unique_suffix}",
                    code=f"EVE_{unique_suffix}",
                    start_time=time(14, 0),
                    end_time=time(22, 0),
                )
            )

            # Assign Morning shift for June 1 to June 30
            a1 = await service.assign_shift(
                ShiftAssignmentCreate(
                    employee_id=emp.id,
                    shift_id=s1.id,
                    effective_from=date(2026, 6, 1),
                    effective_to=date(2026, 6, 30),
                )
            )
            assert a1.id is not None
            assert a1.shift_name == s1.name

            # Attempt overlapping assignment for June 15 to July 15 -> should fail
            with pytest.raises(HTTPException) as exc:
                await service.assign_shift(
                    ShiftAssignmentCreate(
                        employee_id=emp.id,
                        shift_id=s2.id,
                        effective_from=date(2026, 6, 15),
                        effective_to=date(2026, 7, 15),
                    )
                )
            assert exc.value.status_code == 400
            assert "overlapping" in exc.value.detail

            # Non-overlapping assignment for July 1 onwards -> should succeed
            a2 = await service.assign_shift(
                ShiftAssignmentCreate(
                    employee_id=emp.id,
                    shift_id=s2.id,
                    effective_from=date(2026, 7, 1),
                    effective_to=date(2026, 7, 31),
                )
            )
            assert a2.id is not None

    run_async(_test())


def test_cross_midnight_shift_window_resolver(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp = await _get_or_create_org_structure(session, unique_suffix)
            service = ShiftService(session)

            night_shift = await service.create_shift(
                ShiftCreate(
                    name=f"C-Shift Night {unique_suffix}",
                    code=f"C_NIGHT_{unique_suffix}",
                    start_time=time(22, 0),
                    end_time=time(6, 0),
                    begin_check_in_before_minutes=60,
                    allow_check_out_after_minutes=60,
                )
            )

            # Assign night shift for 2026-06-10
            await service.assign_shift(
                ShiftAssignmentCreate(
                    employee_id=emp.id,
                    shift_id=night_shift.id,
                    effective_from=date(2026, 6, 10),
                    effective_to=date(2026, 6, 10),
                )
            )

            # Punch in within buffer: 2026-06-10 21:15 (check-in starts at 21:00)
            window_in = await service.resolve_shift_for_timestamp(
                employee_id=emp.id,
                timestamp=datetime(2026, 6, 10, 21, 15),
            )
            assert window_in is not None
            assert window_in.shift_id == night_shift.id
            assert window_in.is_cross_midnight is True
            assert window_in.shift_start == datetime(2026, 6, 10, 22, 0)
            assert window_in.shift_end == datetime(2026, 6, 11, 6, 0)

            # Punch out next morning: 2026-06-11 06:45 (check-out allowed until 07:00)
            window_out = await service.resolve_shift_for_timestamp(
                employee_id=emp.id,
                timestamp=datetime(2026, 6, 11, 6, 45),
            )
            assert window_out is not None
            assert window_out.shift_id == night_shift.id
            assert window_out.shift_start == datetime(2026, 6, 10, 22, 0)

            # Punch outside window: 2026-06-11 10:00 -> None
            window_none = await service.resolve_shift_for_timestamp(
                employee_id=emp.id,
                timestamp=datetime(2026, 6, 11, 10, 0),
            )
            assert window_none is None

    run_async(_test())


def test_holiday_list_weekly_offs_and_lookup(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, unit, _, _, emp = await _get_or_create_org_structure(session, unique_suffix)
            service = HolidayService(session)

            # Create Holiday List for March 2026 with Sunday weekly offs
            hl = await service.create_holiday_list(
                HolidayListCreate(
                    name=f"March 2026 Calendar {unique_suffix}",
                    unit_id=unit.id,
                    from_date=date(2026, 3, 1),
                    to_date=date(2026, 3, 31),
                    weekly_off_day="Sunday",
                    is_default=True,
                ),
                auto_generate_weekly_offs=True,
            )
            assert hl.id is not None
            # March 2026 has 5 Sundays: 1st, 8th, 15th, 22nd, 29th
            weekly_offs = [h for h in hl.holidays if h.is_weekly_off]
            assert len(weekly_offs) == 5

            # Add a non-weekly-off festival holiday
            fest = await service.add_holiday_to_list(
                hl.id,
                HolidayCreate(
                    holiday_date=date(2026, 3, 25),
                    name="Holi Festival",
                    is_weekly_off=False,
                ),
            )
            assert fest.id is not None

            # Test check holiday
            is_hol, h_name = await service.is_holiday_for_date(
                holiday_list_id=hl.id,
                check_date=date(2026, 3, 25),
            )
            assert is_hol is True
            assert h_name == "Holi Festival"

            # Check a regular workday (March 10 Tuesday)
            is_workday, _ = await service.is_holiday_for_date(
                holiday_list_id=hl.id,
                check_date=date(2026, 3, 10),
            )
            assert is_workday is False

    run_async(_test())


def test_checkin_punch_ingestion_and_deduplication(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp = await _get_or_create_org_structure(session, unique_suffix)
            shift_service = ShiftService(session)
            att_service = AttendanceService(session)

            shift = await shift_service.create_shift(
                ShiftCreate(
                    name=f"General {unique_suffix}",
                    code=f"GEN_{unique_suffix}",
                    start_time=time(9, 0),
                    end_time=time(18, 0),
                    begin_check_in_before_minutes=60,
                    allow_check_out_after_minutes=60,
                )
            )
            await shift_service.assign_shift(
                ShiftAssignmentCreate(
                    employee_id=emp.id,
                    shift_id=shift.id,
                    effective_from=date(2026, 8, 1),
                    effective_to=date(2026, 8, 31),
                )
            )

            punch_time = datetime(2026, 8, 10, 8, 55, 0)

            # 1. Ingest punch using employee_code
            punch1 = await att_service.record_punch(
                AttendancePunchCreate(
                    employee_code=emp.employee_code,
                    punch_time=punch_time,
                    punch_type="IN",
                    device_id="BIO_01",
                    source="BIOMETRIC",
                )
            )
            assert punch1.id is not None
            assert punch1.employee_id == emp.id
            assert punch1.shift_id == shift.id
            assert punch1.is_processed is False

            # 2. Duplicate punch within same second
            punch2 = await att_service.record_punch(
                AttendancePunchCreate(
                    employee_id=emp.id,
                    punch_time=punch_time,
                    punch_type="IN",
                    device_id="BIO_01",
                    source="BIOMETRIC",
                )
            )
            assert punch2.id == punch1.id  # Same punch returned, no duplicate created

            # 3. Bulk punch ingestion
            bulk_res = await att_service.record_bulk_punches(
                BulkPunchCreate(
                    punches=[
                        AttendancePunchCreate(
                            employee_id=emp.id,
                            punch_time=datetime(2026, 8, 10, 18, 5, 0),
                            punch_type="OUT",
                            device_id="BIO_01",
                        ),
                        AttendancePunchCreate(
                            employee_id=emp.id,
                            punch_time=datetime(2026, 8, 11, 9, 2, 0),
                            punch_type="IN",
                            device_id="BIO_01",
                        ),
                    ]
                )
            )
            assert len(bulk_res) == 2

            # 4. List punches
            all_punches = await att_service.list_punches(employee_id=emp.id)
            assert len(all_punches) >= 3

    run_async(_test())
