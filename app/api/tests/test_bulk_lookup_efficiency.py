"""ERP bulk lookups stay bounded while item outcomes retain their ordering."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import event, select

from core.database import async_session_maker, auth_engine
from db.models import AttendanceRecord, Employee
from routers.erp_attendance import sync_records
from routers.erp_overtime import ErpOvertimeRecord, sync_overtime_bulk
from schemas.attendance import ErpAttendanceRecordCreate


@pytest.mark.asyncio(loop_scope="module")
async def test_attendance_bulk_preserves_retries_failures_and_chunk_lookup_count():
    suffix = uuid.uuid4().hex[:8]
    async with async_session_maker() as session:
        employee = Employee(employee_code=f"PA{suffix}", first_name="Bulk")
        session.add(employee)
        await session.commit()
        employee_id = employee.id
        employee_code = employee.employee_code

        day = date(2026, 4, 1)
        first = f"att-{suffix}-first"
        second = f"att-{suffix}-second"
        result = await sync_records([
            ErpAttendanceRecordCreate(employee_code=employee_code, erp_record_id=first,
                                      attendance_date=day, status="PRESENT"),
            ErpAttendanceRecordCreate(employee_code=employee_code, erp_record_id=first,
                                      attendance_date=day, status="PRESENT"),
            ErpAttendanceRecordCreate(employee_code=employee_code, erp_record_id=f"att-{suffix}-bad",
                                      attendance_date=day + timedelta(days=1), shift_id=99999999, status="ABSENT"),
            ErpAttendanceRecordCreate(employee_code=employee_code, erp_record_id=second,
                                      attendance_date=day, status="ABSENT"),
        ], session)
        assert [row["erp_record_id"] for row in result.accepted] == [first, second]
        assert [row["erp_record_id"] for row in result.duplicates] == [first]
        assert len(result.failed) == 1
        record = await session.scalar(select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee_id, AttendanceRecord.attendance_date == day
        ))
        assert record is not None and record.erp_record_id == second and record.status == "ABSENT"

        selects = 0

        def count_select(_connection, _cursor, statement, _parameters, _context, _many):
            nonlocal selects
            if statement.lstrip().upper().startswith("SELECT"):
                selects += 1

        event.listen(auth_engine.sync_engine, "before_cursor_execute", count_select)
        try:
            retry = await sync_records([
                ErpAttendanceRecordCreate(employee_id=employee_id, erp_record_id=second,
                                          attendance_date=day, status="ABSENT")
                for _ in range(500)
            ] + [
                ErpAttendanceRecordCreate(employee_id=employee_id, erp_record_id=f"att-{suffix}-next",
                                          attendance_date=day + timedelta(days=1), status="PRESENT")
            ], session)
        finally:
            event.remove(auth_engine.sync_engine, "before_cursor_execute", count_select)
        assert len(retry.duplicates) == 500 and len(retry.accepted) == 1 and not retry.failed
        assert selects <= 12


@pytest.mark.asyncio(loop_scope="module")
async def test_overtime_bulk_preserves_savepoints_and_chunk_lookup_count():
    suffix = uuid.uuid4().hex[:8]
    async with async_session_maker() as session:
        employee = Employee(employee_code=f"PO{suffix}", first_name="Bulk")
        attendance = AttendanceRecord(employee=employee, attendance_date=date(2026, 4, 1), status="PRESENT")
        session.add_all([employee, attendance])
        await session.commit()

        first = f"ot-{suffix}-first"
        result = await sync_overtime_bulk([
            ErpOvertimeRecord(employee_code=employee.employee_code, attendance_record_id=attendance.id,
                              erp_event_id=first, calculated_minutes=60),
            ErpOvertimeRecord(employee_code=employee.employee_code, attendance_record_id=attendance.id,
                              erp_event_id=first, calculated_minutes=60),
            ErpOvertimeRecord(employee_code=employee.employee_code, attendance_record_id=attendance.id,
                              erp_event_id=f"ot-{suffix}-bad", calculated_minutes=60, status="APPROVED"),
            ErpOvertimeRecord(employee_code=employee.employee_code, attendance_record_id=attendance.id,
                              erp_event_id=f"ot-{suffix}-second", calculated_minutes=30),
        ], session)
        assert len(result["accepted"]) == 2 and len(result["duplicates"]) == 1 and len(result["failed"]) == 1

        selects = 0

        def count_select(_connection, _cursor, statement, _parameters, _context, _many):
            nonlocal selects
            if statement.lstrip().upper().startswith("SELECT"):
                selects += 1

        event.listen(auth_engine.sync_engine, "before_cursor_execute", count_select)
        try:
            retry = await sync_overtime_bulk([
                ErpOvertimeRecord(employee_id=employee.id, attendance_record_id=attendance.id,
                                  erp_event_id=first, calculated_minutes=60)
                for _ in range(500)
            ] + [
                ErpOvertimeRecord(employee_id=employee.id, attendance_record_id=attendance.id,
                                  erp_event_id=f"ot-{suffix}-next", calculated_minutes=15)
            ], session)
        finally:
            event.remove(auth_engine.sync_engine, "before_cursor_execute", count_select)
        assert len(retry["duplicates"]) == 500 and len(retry["accepted"]) == 1 and not retry["failed"]
        assert selects <= 10
