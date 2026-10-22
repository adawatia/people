"""Concurrency tests for leave balance updates.

These tests require a PostgreSQL test database (DATABASE_URL ending in _test).
They exercise the SELECT ... FOR UPDATE path added to apply_leave so concurrent
requests cannot overdraw a leave balance.
"""
from __future__ import annotations

import asyncio
import selectors
import sys
import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy import select

from core.database import async_session_maker
from db.models import (
    Department,
    Designation,
    Employee,
    LeaveAllocation,
    LeaveApplication,
    LeaveBalance,
    LeaveLedgerEntry,
    LeavePeriod,
    LeaveType,
    Organization,
    Unit,
    User,
)
from schemas.shifts import ShiftAssignmentCreate, ShiftCreate
from services.leave_service import LeaveService
from services.shift_service import ShiftService


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


async def _make_approver(session):
    """A real HR user: `actioned_by` is a foreign key, not a free-form id."""
    suffix = uuid.uuid4().hex[:12]
    user = User(
        email=f"approver_{suffix}@example.com",
        username=f"approver_{suffix}",
        hashed_password="not-a-login",
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    # Commit: the session is closed (and uncommitted work discarded) between the
    # test's phases, and the leave row's actioned_by must reference a real user.
    await session.commit()
    return user


async def _create_test_data(session, employee_id, leave_type_id, period_id, allocated=10.0):
    """Create a leave allocation + balance for an employee so they can apply."""
    allocation = LeaveAllocation(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        leave_period_id=period_id,
        new_leaves_allocated=allocated,
        carry_forwarded_leaves=0.0,
        total_leaves_allocated=allocated,
    )
    session.add(allocation)
    await session.flush()

    balance = LeaveBalance(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        year=2026,
        allocated=Decimal(str(allocated)),
    )
    session.add(balance)
    await session.flush()
    return allocation, balance


async def _setup_leave_test(session, suffix):
    # Only one organization may exist (uq_organizations_singleton_key): reuse it
    # rather than inserting one per test.
    org = await session.scalar(select(Organization).order_by(Organization.id))
    if org is None:
        org = Organization(name=f"Org LC {suffix}", short_name=f"LC_{suffix}")
        session.add(org)
        await session.flush()

    unit = Unit(organization_id=org.id, name=f"Unit LC {suffix}", code=f"UC_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Dept LC {suffix}", code=f"DC_{suffix}")
    session.add(dept)
    await session.flush()

    desig = Designation(name=f"Engineer LC {suffix}", code=f"EC_{suffix}")
    session.add(desig)
    await session.flush()

    emp = Employee(
        first_name="Karan",
        last_name="Sharma",
        employee_code=f"LC_{suffix}",
        official_email=f"karan_{suffix}@example.com",
        unit_id=unit.id,
        department_id=dept.id,
        designation_id=desig.id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(emp)
    await session.flush()

    shift_svc = ShiftService(session)
    shift = await shift_svc.create_shift(
        ShiftCreate(
            name=f"General {suffix}",
            code=f"SH_{suffix}",
            start_time=time(9, 0),
            end_time=time(18, 0),
            break_minutes=30,
        )
    )
    await shift_svc.assign_shift(
        ShiftAssignmentCreate(
            employee_id=emp.id,
            shift_id=shift.id,
            effective_from=date(2026, 11, 1),
            effective_to=date(2026, 11, 30),
        )
    )

    period = LeavePeriod(name=f"2026 H2 {suffix}", from_date=date(2026, 7, 1), to_date=date(2026, 12, 31))
    session.add(period)
    await session.flush()

    leave_type = LeaveType(
        name=f"Casual Leave {suffix}",
        code=f"CL_{suffix}",
        is_paid=True,
        annual_allocation=0,
        max_consecutive_days=None,
        requires_approval=True,
        carry_forward=False,
        include_holidays=False,
    )
    session.add(leave_type)
    await session.flush()

    await session.commit()
    return org, unit, dept, desig, emp, shift, period, leave_type


def _conn(record, semaphore, barrier, results):
    """Store a connection object so another task can use it."""
    record.append((semaphore, barrier, results))


class _ReleasableSemaphore(asyncio.Semaphore):
    """An asyncio semaphore whose release() can be called by another task.

    We capture each task's ``acquire`` coroutine and release it from the
    coordinator task once both workers are blocked. This lets us hold two
    transactions at the ``SELECT ... FOR UPDATE`` line at the same time,
    which is the only way to reproduce the race window under asyncio.
    """

    def __init__(self, value=1):
        super().__init__(value)
        self._waiters: list[asyncio.Future] = []

    async def acquire(self) -> None:
        fut = asyncio.get_running_loop().create_future()
        self._waiters.append(fut)
        try:
            await fut
        finally:
            # release_one() already removed the future it resolved.
            if fut in self._waiters:
                self._waiters.remove(fut)

    def release_one(self):
        if self._waiters:
            self._waiters.pop(0).set_result(None)


@pytest.fixture
def unique_suffix():
    import uuid

    return uuid.uuid4().hex[:6]


def test_concurrent_leave_applications_cannot_overdraw(unique_suffix):
    """Two concurrent applications for more leave than available must leave the
    balance correct: one succeeds, one fails, and the final used/pending sum
    equals the single successful application's days.
    """

    async def _concurrent_test():
        async with async_session_maker() as session:
            _, _, _, _, emp, _, period, leave_type = await _setup_leave_test(session, unique_suffix)
            leave_type_id, period_id = leave_type.id, period.id

            _, _ = await _create_test_data(session, emp.id, leave_type_id, period_id, allocated=2.0)
            await session.commit()

        semaphore = _ReleasableSemaphore(value=0)

        async def apply_from(session_factory, worker_id):
            async with session_factory() as session:
                service = LeaveService(session)
                await semaphore.acquire()
                try:
                    from datetime import date

                    # Distinct, non-overlapping ranges so the *balance* lock (not
                    # the overlap guard) is what decides the race.
                    start_day = date(2026, 11, 17) if worker_id == 1 else date(2026, 11, 19)
                    result = await service.apply_leave(
                        type("Payload", (), {
                            "employee_id": emp.id,
                            "leave_type_id": leave_type_id,
                            "from_date": start_day,
                            "to_date": start_day.replace(day=start_day.day + 1),
                            "half_day": False,
                            "half_day_date": None,
                            "reason": f"Worker {worker_id}",
                        })()
                    )
                    semaphore.release_one()
                    return ("ok", result.days_count)
                except Exception as exc:
                    semaphore.release_one()
                    return ("error", str(exc))

        t1 = asyncio.ensure_future(apply_from(async_session_maker, 1))
        t2 = asyncio.ensure_future(apply_from(async_session_maker, 2))
        # Let both tasks start and hit the semaphore before we release it.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        semaphore.release_one()
        semaphore.release_one()
        results = await asyncio.gather(t1, t2)

        ok_results = [r for r in results if r[0] == "ok"]
        err_results = [r for r in results if r[0] != "ok"]

        assert len(ok_results) == 1, (
            f"Expected exactly one successful application; got {len(ok_results)} successes and {len(err_results)} errors"
        )
        assert len(err_results) == 1
        assert "Insufficient leave balance" in err_results[0][1]

        async with async_session_maker() as session:
            used = await session.scalar(
                select(LeaveBalance.used).where(LeaveBalance.employee_id == emp.id, LeaveBalance.leave_type_id == leave_type_id, LeaveBalance.year == 2026)
            )
            pending = await session.scalar(
                select(LeaveBalance.pending).where(LeaveBalance.employee_id == emp.id, LeaveBalance.leave_type_id == leave_type_id, LeaveBalance.year == 2026)
            )
            applications = await session.scalars(
                select(LeaveApplication).where(LeaveApplication.employee_id == emp.id, LeaveApplication.leave_type_id == leave_type_id)
            )
            apps = list(applications.all())

        # apply_leave reserves against `pending`, it does not consume `used`.
        assert pending == Decimal("2.0"), f"Pending should be 2.0 (one 2-day application); got {pending}"
        assert used == Decimal("0.0"), f"Used should stay 0.0 for a pending application; got {used}"
        assert len(apps) == 1
        assert apps[0].status == "PENDING"

    run_async(_concurrent_test())


def test_approved_leave_balance_reverts_on_cancel(unique_suffix):
    """Approving then cancelling a pending application must restore the balance
    correctly: used decreases and a reversal ledger entry is written.
    """

    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, _, period, leave_type = await _setup_leave_test(session, unique_suffix)
            leave_type_id, period_id = leave_type.id, period.id

            _, _ = await _create_test_data(session, emp.id, leave_type_id, period_id, allocated=5.0)
            await session.commit()

        async with async_session_maker() as session:
            service = LeaveService(session)
            app = await service.apply_leave(
                type("Payload", (), {
                    "employee_id": emp.id,
                    "leave_type_id": leave_type_id,                            "from_date": date(2026, 11, 18),
                            "to_date": date(2026, 11, 19),
                    "half_day": False,
                    "half_day_date": None,
                    "reason": "Approve-cancel test",
                })()
            )
            assert app.status == "PENDING"
            assert app.days_count == 2.0

            app = await service.approve_leave(app.id, (await _make_approver(session)).id)
            assert app.status == "APPROVED"

        async with async_session_maker() as session:
            balance = await session.scalar(
                select(LeaveBalance).where(LeaveBalance.employee_id == emp.id, LeaveBalance.leave_type_id == leave_type_id, LeaveBalance.year == 2026)
            )
            assert balance is not None
            assert balance.used == Decimal("2.0")
            assert balance.pending == Decimal("0.0")

            app = await session.scalar(select(LeaveApplication).where(LeaveApplication.id == app.id))
            cancelled = await LeaveService(session).cancel_leave(app.id, (await _make_approver(session)).id)
            assert cancelled.status == "CANCELLED"

            # The cancellation ran in another transaction; drop the cached row
            # so the assertions read what was actually committed.
            session.expire_all()
            balance = await session.scalar(
                select(LeaveBalance).where(LeaveBalance.employee_id == emp.id, LeaveBalance.leave_type_id == leave_type_id, LeaveBalance.year == 2026)
            )
            assert balance.used == Decimal("0.0")

            reversal_count = await session.scalar(
                select(LeaveLedgerEntry).where(
                    LeaveLedgerEntry.employee_id == emp.id,
                    LeaveLedgerEntry.leave_type_id == leave_type_id,
                    LeaveLedgerEntry.transaction_type == "REVERSAL",
                )
            )
            assert reversal_count is not None

    run_async(_test())


def test_rejected_pending_restores_pending(unique_suffix):
    """Rejecting a pending paid leave must reduce pending without touching used."""

    async def _test():
        async with async_session_maker() as session:
            _, _, _, _, emp, _, period, leave_type = await _setup_leave_test(session, unique_suffix)
            leave_type_id, period_id = leave_type.id, period.id

            _, _ = await _create_test_data(session, emp.id, leave_type_id, period_id, allocated=5.0)
            await session.commit()

        async with async_session_maker() as session:
            service = LeaveService(session)
            app = await service.apply_leave(
                type("Payload", (), {
                    "employee_id": emp.id,
                    "leave_type_id": leave_type_id,                            "from_date": date(2026, 11, 25),
                            "to_date": date(2026, 11, 26),
                    "half_day": False,
                    "half_day_date": None,
                    "reason": "Reject test",
                })()
            )
            assert app.status == "PENDING"
            assert app.days_count == 2.0

            app = await service.reject_leave(
                app.id, (await _make_approver(session)).id, rejection_reason="Not now"
            )
            assert app.status == "REJECTED"

        async with async_session_maker() as session:
            balance = await session.scalar(
                select(LeaveBalance).where(LeaveBalance.employee_id == emp.id, LeaveBalance.leave_type_id == leave_type_id, LeaveBalance.year == 2026)
            )
            assert balance.pending == Decimal("0.0")
            assert balance.used == Decimal("0.0")

    run_async(_test())
