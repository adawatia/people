"""ERP sync status and reconciliation behaviour.

Requires the PostgreSQL test database.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from core.database import async_session_maker
from core.erp_auth import ErpPrincipal
from db.models import AttendanceRecord, Employee, LeaveBalance, LeaveType
from routers.erp_attendance import sync_records
from routers.erp_leaves import ErpLeaveBalance
from routers.erp_operations import (
    AttendanceReconciliationRequest,
    LeaveBalanceReconciliationRequest,
    get_sync_status,
    reconcile_attendance,
    reconcile_leave_balances,
)
from schemas.attendance import ErpAttendanceRecordCreate

PRINCIPAL = ErpPrincipal(client_id="ops-client", scopes=frozenset({"*"}))
DAY = date(2027, 1, 11)


@pytest.mark.asyncio
async def test_sync_status_reports_backlog_and_nonce_backend():
    async with async_session_maker() as session:
        status = await get_sync_status(session)
        assert status.stale_after_seconds > 0
        assert status.feed.pending_events >= 0
        assert status.nonce.backend in {"memory", "redis"}
        assert status.nonce.replay_protection_shared is (status.nonce.backend == "redis")
        assert isinstance(status.entities, list)


@pytest.mark.asyncio
async def test_reconciliation_detects_mismatch_and_missing_without_writing():
    async with async_session_maker() as session:
        suffix = uuid.uuid4().hex[:8]
        employee = Employee(employee_code=f"RC{suffix}", first_name="Reconcile")
        session.add(employee)
        await session.commit()
        erp_id = f"rc-{suffix}"

        await sync_records(
            [
                ErpAttendanceRecordCreate(
                    employee_id=employee.id,
                    erp_record_id=erp_id,
                    attendance_date=DAY,
                    status="PRESENT",
                    worked_minutes=480,
                )
            ],
            session,
        )

        request = AttendanceReconciliationRequest(
            from_date=DAY,
            to_date=DAY,
            records=[
                ErpAttendanceRecordCreate(
                    employee_id=employee.id,
                    erp_record_id=erp_id,
                    attendance_date=DAY,
                    status="PRESENT",
                    worked_minutes=400,
                )
            ],
        )
        result = await reconcile_attendance(request, principal=PRINCIPAL, session=session)
        assert result.apply is False
        # The window may contain rows from other runs, so identify this record.
        mismatch = next(item for item in result.discrepancies if item.erp_record_id == erp_id)
        assert mismatch.kind == "mismatched"
        assert mismatch.fields["worked_minutes"] == {"hrms": 480, "erp": 400}

        # Dry run: the local row is untouched.
        row = await session.scalar(select(AttendanceRecord).where(AttendanceRecord.erp_record_id == erp_id))
        await session.refresh(row)
        assert row.worked_minutes == 480


@pytest.mark.asyncio
async def test_reconciliation_reports_missing_in_erp_and_unknown_employee():
    async with async_session_maker() as session:
        suffix = uuid.uuid4().hex[:8]
        employee = Employee(employee_code=f"RE{suffix}", first_name="Reconcile")
        session.add(employee)
        await session.commit()
        erp_id = f"re-{suffix}"
        await sync_records(
            [
                ErpAttendanceRecordCreate(
                    employee_id=employee.id,
                    erp_record_id=erp_id,
                    attendance_date=DAY,
                    status="PRESENT",
                )
            ],
            session,
        )

        request = AttendanceReconciliationRequest(
            from_date=DAY,
            to_date=DAY,
            records=[
                ErpAttendanceRecordCreate(
                    employee_code="NO-SUCH-EMPLOYEE",
                    erp_record_id=f"re-{suffix}-ghost",
                    attendance_date=DAY,
                    status="PRESENT",
                )
            ],
        )
        result = await reconcile_attendance(request, principal=PRINCIPAL, session=session)
        assert any(
            item.kind == "unknown_employee" and item.erp_record_id == f"re-{suffix}-ghost"
            for item in result.discrepancies
        )
        assert any(
            item.kind == "missing_in_erp" and item.erp_record_id == erp_id for item in result.discrepancies
        )


@pytest.mark.asyncio
async def test_reconciliation_apply_runs_the_audited_sync_path():
    async with async_session_maker() as session:
        suffix = uuid.uuid4().hex[:8]
        employee = Employee(employee_code=f"RA{suffix}", first_name="Reconcile")
        session.add(employee)
        await session.commit()
        erp_id = f"ra-{suffix}"
        await sync_records(
            [
                ErpAttendanceRecordCreate(
                    employee_id=employee.id,
                    erp_record_id=erp_id,
                    attendance_date=DAY,
                    status="PRESENT",
                    worked_minutes=480,
                )
            ],
            session,
        )

        request = AttendanceReconciliationRequest(
            from_date=DAY,
            to_date=DAY,
            apply=True,
            records=[
                ErpAttendanceRecordCreate(
                    employee_id=employee.id,
                    erp_record_id=erp_id,
                    attendance_date=DAY,
                    status="PRESENT",
                    worked_minutes=420,
                )
            ],
        )
        result = await reconcile_attendance(request, principal=PRINCIPAL, session=session)
        assert result.applied is not None and result.applied.accepted_count == 1

        row = await session.scalar(select(AttendanceRecord).where(AttendanceRecord.erp_record_id == erp_id))
        await session.refresh(row)
        assert row.worked_minutes == 420


@pytest.mark.asyncio
async def test_leave_balance_reconciliation_is_dry_run_by_default():
    async with async_session_maker() as session:
        suffix = uuid.uuid4().hex[:8]
        employee = Employee(employee_code=f"LB{suffix}", first_name="Balance")
        leave_type = LeaveType(name=f"Balance Leave {suffix}", code=f"LB{suffix}")
        session.add_all([employee, leave_type])
        await session.flush()
        balance = LeaveBalance(
            employee_id=employee.id, leave_type_id=leave_type.id, year=2027, allocated=10, used=2, pending=0
        )
        session.add(balance)
        await session.commit()

        request = LeaveBalanceReconciliationRequest(
            balances=[
                ErpLeaveBalance(
                    employee_id=employee.id,
                    leave_code=leave_type.code,
                    year=2027,
                    allocated=12,
                    used=2,
                    pending=1,
                )
            ]
        )
        result = await reconcile_leave_balances(request, principal=PRINCIPAL, session=session)
        assert result.discrepancy_count == 1
        assert result.discrepancies[0].fields["allocated"] == {"hrms": 10.0, "erp": 12.0}
        await session.refresh(balance)
        assert float(balance.allocated) == 10.0

        applied = LeaveBalanceReconciliationRequest(
            balances=request.balances,
            apply=True,
        )
        outcome = await reconcile_leave_balances(applied, principal=PRINCIPAL, session=session)
        assert outcome.applied is not None and outcome.applied.accepted_count == 1
        await session.refresh(balance)
        assert float(balance.allocated) == 12.0
