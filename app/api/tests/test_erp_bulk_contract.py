"""The shared ERP bulk contract: envelope, safe errors, audit, ownership.

Requires the PostgreSQL test database.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi import Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from core.database import async_session_maker
from core.erp_auth import ErpPrincipal
from core.erp_batch import (
    ErpItemError,
    apply_batch_status,
    classify_erp_error,
    new_batch,
)
from db.models import AttendanceRecord, Employee, ErpSyncBatch, Holiday, HolidayList
from routers.erp_attendance import sync_records_bulk
from routers.erp_holidays import ErpHoliday, sync_holidays_bulk
from routers.erp_overtime import ErpOvertimeRecord, sync_overtime_bulk
from schemas.attendance import ErpAttendanceRecordBulkCreate, ErpAttendanceRecordCreate

PRINCIPAL = ErpPrincipal(client_id="contract-client", scopes=frozenset({"*"}))


@pytest.mark.asyncio
async def test_attendance_bulk_returns_the_envelope_and_records_the_batch():
    async with async_session_maker() as session:
        suffix = uuid.uuid4().hex[:8]
        employee = Employee(employee_code=f"BC{suffix}", first_name="Contract")
        session.add(employee)
        await session.commit()

        response = Response()
        payload = ErpAttendanceRecordBulkCreate(
            records=[
                ErpAttendanceRecordCreate(
                    employee_id=employee.id,
                    erp_record_id=f"bc-{suffix}",
                    attendance_date=date(2026, 12, 21),
                    status="PRESENT",
                    worked_minutes=480,
                ),
                ErpAttendanceRecordCreate(
                    employee_code="NO-SUCH",
                    erp_record_id=f"bc-{suffix}-bad",
                    attendance_date=date(2026, 12, 21),
                    status="PRESENT",
                ),
            ]
        )
        result = await sync_records_bulk(
            response, payload, batch_id=f"contract-{suffix}", principal=PRINCIPAL, session=session
        )

        assert result.batch_id == f"contract-{suffix}"
        assert response.headers["X-ERP-Batch-Id"] == result.batch_id
        assert result.received_count == 2
        assert result.accepted_count == 1 and result.failed_count == 1
        assert result.retryable_failed_count == 0

        audit = await session.get(ErpSyncBatch, result.batch_id)
        assert audit is not None
        assert audit.endpoint == "attendance.records.bulk"
        assert audit.accepted_count == 1 and audit.failed_count == 1
        assert audit.last_error_code == "EMPLOYEE_NOT_FOUND"
        assert audit.client_id == PRINCIPAL.client_id


@pytest.mark.asyncio
async def test_item_failures_never_leak_internal_detail():
    async with async_session_maker() as session:
        suffix = uuid.uuid4().hex[:8]
        payload = ErpAttendanceRecordBulkCreate(
            records=[
                ErpAttendanceRecordCreate(
                    employee_code=f"missing-{suffix}",
                    erp_record_id=f"leak-{suffix}",
                    attendance_date=date(2026, 12, 22),
                    status="PRESENT",
                )
            ]
        )
        result = await sync_records_bulk(
            Response(), payload, batch_id=f"leak-{suffix}", principal=PRINCIPAL, session=session
        )
        failure = result.items[0]
        assert failure.status == "failed"
        assert failure.code == "EMPLOYEE_NOT_FOUND"
        for forbidden in ("Traceback", "SELECT", "asyncpg", "psycopg", "INSERT INTO"):
            assert forbidden not in (failure.message or "")


def test_error_classification_separates_transient_from_permanent():
    assert classify_erp_error(ErpItemError("BAD_INPUT", "Nope"))[:2] == ("BAD_INPUT", "Nope")
    assert classify_erp_error(ErpItemError("BAD_INPUT", "Nope"))[2] is False

    conflict = IntegrityError("stmt", {}, Exception("duplicate key"))
    code, _, retryable = classify_erp_error(conflict)
    assert (code, retryable) == ("CONFLICT", False)

    transient = OperationalError("stmt", {}, Exception("connection reset"))
    code, message, retryable = classify_erp_error(transient)
    assert (code, retryable) == ("TRANSIENT_PERSISTENCE_ERROR", True)
    assert "connection reset" not in message

    code, message, retryable = classify_erp_error(RuntimeError("secret sql detail"))
    assert (code, retryable) == ("INTERNAL_ERROR", True)
    assert "secret sql detail" not in message


def test_whole_batch_transient_failure_reports_503_with_retry_after():
    result = new_batch("attendance.records.bulk", "batch-123456", 2)
    result.add_failure("a", code="TRANSIENT_PERSISTENCE_ERROR", message="retry", retryable=True)
    result.add_failure("b", code="TRANSIENT_PERSISTENCE_ERROR", message="retry", retryable=True)

    response = Response()
    apply_batch_status(response, result)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"


def test_permanent_item_failure_keeps_200():
    result = new_batch("attendance.records.bulk", "batch-abcdef", 1)
    result.add_failure("a", code="VALIDATION_ERROR", message="bad", retryable=False)

    response = Response()
    apply_batch_status(response, result)
    assert response.status_code == 200
    assert "Retry-After" not in response.headers


def test_empty_batches_are_rejected_before_any_write():
    with pytest.raises(ValidationError):
        ErpAttendanceRecordBulkCreate(records=[])


async def _free_holiday_date(session) -> date:
    """Pick a date the calendar does not use yet (the test DB persists runs)."""
    base = date(2030, 1, 1)
    taken = set(
        (
            await session.execute(
                select(Holiday.holiday_date).where(Holiday.holiday_date >= base)
            )
        ).scalars()
    )
    offset = int(uuid.uuid4().hex[:6], 16) % 3650
    for _ in range(3650):
        candidate = base + timedelta(days=offset)
        if candidate not in taken:
            return candidate
        offset = (offset + 1) % 3650
    raise AssertionError("no free holiday date available for the test")


@pytest.mark.asyncio
async def test_duplicate_holiday_and_date_conflict_are_reported_separately():
    async with async_session_maker() as session:
        suffix = uuid.uuid4().hex[:8]
        first_id = f"hol-{suffix}-a"
        second_id = f"hol-{suffix}-b"
        holiday_date = await _free_holiday_date(session)

        first = await sync_holidays_bulk(
            [ErpHoliday(erp_holiday_id=first_id, name="Republic Day", holiday_date=holiday_date)],
            session,
            batch_id=f"hol-{suffix}",
        )
        assert first.accepted_count == 1

        replay = await sync_holidays_bulk(
            [ErpHoliday(erp_holiday_id=first_id, name="Republic Day", holiday_date=holiday_date)],
            session,
        )
        assert replay.duplicate_count == 1

        conflict = await sync_holidays_bulk(
            [ErpHoliday(erp_holiday_id=second_id, name="Other", holiday_date=holiday_date)],
            session,
        )
        assert conflict.failed_count == 1
        assert conflict.items[0].code == "HOLIDAY_DATE_CONFLICT"

        calendar = await session.scalar(select(HolidayList).where(HolidayList.is_default.is_(True)))
        rows = (
            await session.execute(
                select(Holiday).where(
                    Holiday.holiday_list_id == calendar.id, Holiday.holiday_date == holiday_date
                )
            )
        ).scalars().all()
        assert [row.erp_holiday_id for row in rows] == [first_id]


@pytest.mark.asyncio
async def test_erp_cannot_set_overtime_status_or_approve_minutes():
    async with async_session_maker() as session:
        suffix = uuid.uuid4().hex[:8]
        employee = Employee(employee_code=f"OT{suffix}", first_name="Overtime")
        session.add(employee)
        await session.flush()
        attendance = AttendanceRecord(
            employee_id=employee.id, attendance_date=date(2026, 12, 23), status="PRESENT"
        )
        session.add(attendance)
        await session.commit()

        result = await sync_overtime_bulk(
            [
                ErpOvertimeRecord(
                    erp_event_id=f"ot-{suffix}-a",
                    employee_id=employee.id,
                    attendance_record_id=attendance.id,
                    calculated_minutes=60,
                ),
                ErpOvertimeRecord(
                    erp_event_id=f"ot-{suffix}-b",
                    employee_id=employee.id,
                    attendance_record_id=attendance.id,
                    calculated_minutes=60,
                    status="APPROVED",
                ),
                ErpOvertimeRecord(
                    erp_event_id=f"ot-{suffix}-c",
                    employee_id=employee.id,
                    attendance_record_id=attendance.id,
                    calculated_minutes=60,
                    approved_minutes=30,
                ),
            ],
            session,
        )
        assert result.accepted_count == 1
        codes = {item.code for item in result.items if item.status == "failed"}
        assert codes == {"OVERTIME_STATUS_NOT_ERP_OWNED", "OVERTIME_APPROVAL_NOT_ERP_OWNED"}
