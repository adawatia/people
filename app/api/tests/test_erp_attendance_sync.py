"""ERP attendance ingestion: identity, corrections, conflicts, and races.

Requires the PostgreSQL test database. Concurrency cases open two real sessions
against it; they are not simulated with mocks.
"""

import asyncio
import uuid
from datetime import date, time

import pytest
from sqlalchemy import select

from core.database import async_session_maker
from db.models import AttendanceRecord, AuditLog, Employee, Shift
from routers.erp_attendance import sync_records
from schemas.attendance import ErpAttendanceRecordCreate

DAY = date(2026, 12, 7)


async def _employee(session, suffix=None) -> Employee:
    suffix = suffix or uuid.uuid4().hex[:8]
    employee = Employee(employee_code=f"AT{suffix}", first_name="Attend")
    session.add(employee)
    await session.flush()
    return employee


def _record(employee: Employee, erp_id: str, **overrides) -> ErpAttendanceRecordCreate:
    payload = {
        "employee_id": employee.id,
        "erp_record_id": erp_id,
        "attendance_date": DAY,
        "status": "PRESENT",
        "punch_in": time(9, 0),
        "punch_out": time(18, 0),
        "worked_minutes": 480,
    }
    payload.update(overrides)
    return ErpAttendanceRecordCreate(**payload)


def _items(result, status):
    return [item for item in result.items if item.status == status]


@pytest.mark.asyncio
async def test_replaying_an_identical_record_is_a_duplicate_without_a_second_row():
    async with async_session_maker() as session:
        employee = await _employee(session)
        await session.commit()
        erp_id = f"att-{uuid.uuid4().hex}"

        first = await sync_records([_record(employee, erp_id)], session)
        assert [item.key for item in _items(first, "accepted")] == [erp_id]

        replay = await sync_records([_record(employee, erp_id)], session)
        assert [item.key for item in _items(replay, "duplicate")] == [erp_id]
        rows = (
            await session.execute(
                select(AttendanceRecord).where(AttendanceRecord.erp_record_id == erp_id)
            )
        ).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_changed_values_with_the_same_id_are_an_audited_correction():
    async with async_session_maker() as session:
        employee = await _employee(session)
        await session.commit()
        erp_id = f"att-{uuid.uuid4().hex}"
        await sync_records([_record(employee, erp_id)], session)

        corrected = await sync_records([_record(employee, erp_id, worked_minutes=420)], session)
        assert [item.key for item in _items(corrected, "accepted")] == [erp_id]
        row = await session.scalar(select(AttendanceRecord).where(AttendanceRecord.erp_record_id == erp_id))
        await session.refresh(row)
        assert row.worked_minutes == 420

        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "ERP_ATTENDANCE_CORRECTED",
                AuditLog.filters_json.like(f"%{erp_id}%"),
            )
        )
        assert audit is not None
        assert "worked_minutes" in audit.filters_json


@pytest.mark.asyncio
async def test_a_different_erp_id_cannot_take_over_an_occupied_employee_date():
    async with async_session_maker() as session:
        employee = await _employee(session)
        await session.commit()
        first_id = f"att-{uuid.uuid4().hex}"
        second_id = f"att-{uuid.uuid4().hex}"
        await sync_records([_record(employee, first_id)], session)

        conflict = await sync_records([_record(employee, second_id, status="ABSENT")], session)
        failed = _items(conflict, "failed")
        assert [item.key for item in failed] == [second_id]
        assert failed[0].code == "ATTENDANCE_RECORD_CONFLICT"
        assert failed[0].retryable is False

        row = await session.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == employee.id, AttendanceRecord.attendance_date == DAY
            )
        )
        assert row.erp_record_id == first_id and row.status == "PRESENT"


@pytest.mark.asyncio
async def test_an_erp_record_id_cannot_move_to_another_date():
    async with async_session_maker() as session:
        employee = await _employee(session)
        await session.commit()
        erp_id = f"att-{uuid.uuid4().hex}"
        await sync_records([_record(employee, erp_id)], session)

        moved = await sync_records(
            [_record(employee, erp_id, attendance_date=date(2026, 12, 8))], session
        )
        failed = _items(moved, "failed")
        assert failed[0].code == "ERP_RECORD_ID_CONFLICT"
        assert failed[0].retryable is False


@pytest.mark.asyncio
async def test_erp_adopts_an_hrms_created_row_for_the_same_day():
    async with async_session_maker() as session:
        employee = await _employee(session)
        existing = AttendanceRecord(
            employee_id=employee.id, attendance_date=DAY, status="ON_LEAVE", source="HRMS"
        )
        session.add(existing)
        await session.commit()
        erp_id = f"att-{uuid.uuid4().hex}"

        result = await sync_records([_record(employee, erp_id, status="ABSENT", worked_minutes=0)], session)
        assert [item.key for item in _items(result, "accepted")] == [erp_id]
        await session.refresh(existing)
        assert existing.erp_record_id == erp_id
        assert existing.source == "ERP" and existing.status == "ABSENT"

        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "ERP_ATTENDANCE_ADOPTED",
                AuditLog.filters_json.like(f"%{erp_id}%"),
            )
        )
        assert audit is not None and "ON_LEAVE" in audit.filters_json


@pytest.mark.asyncio
async def test_an_omitted_shift_does_not_clear_the_existing_one():
    async with async_session_maker() as session:
        employee = await _employee(session)
        shift = Shift(name=f"Shift {uuid.uuid4().hex[:6]}", start_time=time(9, 0), end_time=time(18, 0))
        session.add(shift)
        await session.commit()
        erp_id = f"att-{uuid.uuid4().hex}"

        await sync_records([_record(employee, erp_id, shift_id=shift.id)], session)
        result = await sync_records([_record(employee, erp_id, worked_minutes=400)], session)
        assert [item.key for item in _items(result, "accepted")] == [erp_id]
        row = await session.scalar(select(AttendanceRecord).where(AttendanceRecord.erp_record_id == erp_id))
        await session.refresh(row)
        assert row.shift_id == shift.id and row.worked_minutes == 400


@pytest.mark.asyncio
async def test_unknown_employee_and_shift_fail_with_permanent_codes():
    async with async_session_maker() as session:
        employee = await _employee(session)
        await session.commit()

        result = await sync_records(
            [
                _record(employee, f"att-{uuid.uuid4().hex}", shift_id=987654321),
                ErpAttendanceRecordCreate(
                    employee_code="NO-SUCH-EMPLOYEE",
                    erp_record_id=f"att-{uuid.uuid4().hex}",
                    attendance_date=DAY,
                    status="PRESENT",
                ),
            ],
            session,
        )
        failed = _items(result, "failed")
        assert {item.code for item in failed} == {"SHIFT_NOT_FOUND", "EMPLOYEE_NOT_FOUND"}
        assert all(item.retryable is False for item in failed)
        assert result.accepted_count == 0 and result.received_count == 2


@pytest.mark.asyncio
async def test_concurrent_identical_chunks_produce_one_row_one_duplicate():
    async with async_session_maker() as session:
        employee = await _employee(session)
        await session.commit()
        employee_id = employee.id
    erp_id = f"att-{uuid.uuid4().hex}"

    async def worker():
        async with async_session_maker() as session:
            return await sync_records(
                [
                    ErpAttendanceRecordCreate(
                        employee_id=employee_id,
                        erp_record_id=erp_id,
                        attendance_date=DAY,
                        status="PRESENT",
                        worked_minutes=480,
                    )
                ],
                session,
            )

    results = await asyncio.gather(worker(), worker())
    statuses = sorted(result.items[0].status for result in results)
    assert statuses == ["accepted", "duplicate"]

    async with async_session_maker() as session:
        rows = (
            await session.execute(select(AttendanceRecord).where(AttendanceRecord.erp_record_id == erp_id))
        ).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_mixed_batch_commits_valid_items_and_a_retry_is_idempotent():
    async with async_session_maker() as session:
        employee = await _employee(session)
        await session.commit()
        good = f"att-{uuid.uuid4().hex}"
        bad = f"att-{uuid.uuid4().hex}"

        result = await sync_records(
            [
                _record(employee, good),
                # Different day: a second id for the *same* day could never be
                # accepted, even after the shift is fixed.
                _record(employee, bad, attendance_date=date(2026, 12, 9), shift_id=111111),
            ],
            session,
        )
        assert result.accepted_count == 1 and result.failed_count == 1
        assert [item.key for item in _items(result, "accepted")] == [good]

        # Retrying the whole page after fixing the bad row is safe.
        retry = await sync_records(
            [_record(employee, good), _record(employee, bad, attendance_date=date(2026, 12, 9))], session
        )
        assert [item.key for item in _items(retry, "duplicate")] == [good]
        assert [item.key for item in _items(retry, "accepted")] == [bad]
