"""Regression tests for batched shift schedule resolution.

Covers the ShiftScheduleContext behaviour introduced when the schedule
lookups moved from one query per calendar date (a 15-day N+1 on the
employee dashboard) to a single batched range query.
"""

import asyncio
import selectors
import sys
import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from core.database import async_session_maker
from db.models import Department, Designation, Employee, Organization, Unit, now_ist
from schemas.shifts import ShiftAssignmentCreate, ShiftCreate
from services.shift_service import ShiftService


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def today() -> date:
    """IST "today" — the same convention the service layer uses."""
    return now_ist().date()


@pytest.fixture
def unique_suffix():
    return uuid.uuid4().hex[:6]


async def _get_or_create_org_structure(session, suffix: str):
    org = await session.scalar(select(Organization).order_by(Organization.id.asc()))
    if org is None:
        org = Organization(name=f"Org Shift Batch {suffix}", short_name=f"OSB_{suffix}")
        session.add(org)
        await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit Shift Batch {suffix}", code=f"USB_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Dept Shift Batch {suffix}", code=f"DSB_{suffix}")
    session.add(dept)
    await session.flush()

    desig = Designation(name=f"Eng Shift Batch {suffix}", code=f"ESB_{suffix}")
    session.add(desig)
    await session.flush()

    emp = Employee(
        first_name="Asha",
        last_name="Nair",
        employee_code=f"EMP_OSB_{suffix}",
        official_email=f"asha_{suffix}@example.com",
        department_id=dept.id,
        unit_id=unit.id,
        designation_id=desig.id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(emp)
    await session.flush()
    await session.commit()
    return org, unit, dept, desig, emp


def test_batched_context_matches_per_date_resolution(unique_suffix):
    """The batched context resolves the same windows the per-date path did."""

    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp = await _get_or_create_org_structure(session, unique_suffix)
            service = ShiftService(session)

            day_shift = await service.create_shift(
                ShiftCreate(name=f"Day {unique_suffix}", code=f"DY_{unique_suffix}",
                            start_time=time(9, 0), end_time=time(18, 0))
            )
            night_shift = await service.create_shift(
                ShiftCreate(name=f"Night {unique_suffix}", code=f"NT_{unique_suffix}",
                            start_time=time(22, 0), end_time=time(6, 0))
            )

            # A dated assignment ending last week and an open-ended one
            # starting today: the context must resolve both eras correctly.
            await service.assign_shift(
                ShiftAssignmentCreate(employee_id=emp.id, shift_id=night_shift.id,
                                      effective_from=today() - timedelta(days=30),
                                      effective_to=today() - timedelta(days=7))
            )
            await service.assign_shift(
                ShiftAssignmentCreate(employee_id=emp.id, shift_id=day_shift.id,
                                      effective_from=today(), effective_to=None)
            )

            context = await service.load_schedule_context(
                emp.id,
                start_date=today() - timedelta(days=1),
                end_date=today() + timedelta(days=14),
            )

            # One assignment query covers the whole range: only the open-ended
            # day-shift assignment overlaps it, which is exactly the batching
            # win — the old code re-queried per date to learn the same thing.
            assert len(context.assignments) == 1

            assert context.assignments_for_date(today() - timedelta(days=10)) == []
            assert context.assignments_for_date(today())[0].shift_id == day_shift.id
            assert context.assignments_for_date(today() + timedelta(days=14))[0].shift_id == day_shift.id

            # Window resolution matches the dedicated per-date service method
            # for every date in the loaded range.
            for offset in range(-1, 15):
                day = today() + timedelta(days=offset)
                from_context = service._window_for_date(context, day)
                per_date = await service.get_shift_window_for_date(emp.id, day)
                assert (from_context is None) == (per_date is None)
                if from_context is not None:
                    assert from_context.shift_id == per_date.shift_id
                    assert from_context.shift_start == per_date.shift_start

    run_async(_test())


def test_shift_window_for_date_outside_context_falls_back_to_default(unique_suffix):
    """Dates outside the loaded range still resolve via the default shift."""

    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp = await _get_or_create_org_structure(session, unique_suffix)
            service = ShiftService(session)

            shift = await service.create_shift(
                ShiftCreate(name=f"Default {unique_suffix}", code=f"DF_{unique_suffix}",
                            start_time=time(9, 0), end_time=time(18, 0))
            )
            emp.shift_id = shift.id
            await session.commit()

            far_past = today() - timedelta(days=60)
            window = await service.get_shift_window_for_date(emp.id, far_past)
            assert window is not None
            assert window.shift_id == shift.id
            assert window.shift_start.date() == far_past

            # No default shift and no assignment -> no window at all.
            emp.shift_id = None
            await session.commit()
            assert await service.get_shift_window_for_date(emp.id, far_past) is None

    run_async(_test())


def test_schedule_upcoming_search_and_schedule_schema(unique_suffix):
    """The 15-day upcoming search still finds the next scheduled start."""

    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp = await _get_or_create_org_structure(session, unique_suffix)
            service = ShiftService(session)

            day_shift = await service.create_shift(
                ShiftCreate(name=f"NineToFive {unique_suffix}", code=f"NTF_{unique_suffix}",
                            start_time=time(9, 0), end_time=time(17, 0))
            )
            await service.assign_shift(
                ShiftAssignmentCreate(employee_id=emp.id, shift_id=day_shift.id,
                                      effective_from=today() - timedelta(days=1),
                                      effective_to=None)
            )

            schedule = await service.get_employee_shift_schedule(emp.id)
            assert schedule.assigned_shift is not None
            assert schedule.assigned_shift.shift_id == day_shift.id
            # previous_shift is the shift scheduled on yesterday's date.
            assert schedule.previous_shift is not None
            assert schedule.previous_shift.shift_id == day_shift.id
            assert schedule.upcoming_shift is not None
            assert schedule.upcoming_shift.shift_start > schedule.assigned_shift.shift_start

    run_async(_test())


def test_employee_visible_shifts_single_query(unique_suffix):
    """The employee-visible shift list comes from one batched repo query."""

    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp = await _get_or_create_org_structure(session, unique_suffix)
            service = ShiftService(session)

            general = await service.create_shift(
                ShiftCreate(name=f"General {unique_suffix}", code=f"GN_{unique_suffix}",
                            start_time=time(9, 0), end_time=time(18, 0))
            )
            future = await service.create_shift(
                ShiftCreate(name=f"Future {unique_suffix}", code=f"FT_{unique_suffix}",
                            start_time=time(14, 0), end_time=time(22, 0))
            )
            inactive = await service.create_shift(
                ShiftCreate(name=f"Inactive {unique_suffix}", code=f"IN_{unique_suffix}",
                            start_time=time(6, 0), end_time=time(14, 0))
            )
            inactive_shift = await service.repo.get_by_id(inactive.id)
            inactive_shift.is_active = False
            await session.commit()

            await service.assign_shift(
                ShiftAssignmentCreate(employee_id=emp.id, shift_id=general.id,
                                      effective_from=today() - timedelta(days=1), effective_to=None)
            )

            # Simulate a future rotation by inserting a second assignment row
            # directly (assign_shift would reject the overlap by design).
            from db.models import ShiftAssignment
            session.add(ShiftAssignment(employee_id=emp.id, shift_id=future.id,
                                        effective_from=today() + timedelta(days=7),
                                        effective_to=today() + timedelta(days=9),
                                        status="ACTIVE"))
            await session.commit()

            shifts = await service.repo.list_active_assignment_shifts(emp.id)
            names = {shift.name for shift in shifts}
            # The current shift is always visible; the future rotation is
            # within the horizon; inactive definitions are excluded.
            assert general.name in names
            assert future.name in names
            assert inactive.name not in names

    run_async(_test())
