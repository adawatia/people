"""ERP-owned processed attendance synchronization."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.erp_auth import require_erp_scope
from db.models import AttendanceRecord, Employee, Shift, now_ist
from schemas.attendance import ErpAttendanceRecordBulkCreate, ErpAttendanceRecordCreate, ErpSyncResult

router = APIRouter(prefix="/integrations/erp/attendance", tags=["erp-attendance"])


async def _employee(session: AsyncSession, employee_id: int | None, employee_code: str | None) -> Employee:
    employee = await session.get(Employee, employee_id) if employee_id is not None else None
    if employee is None and employee_code:
        employee = await session.scalar(select(Employee).where(Employee.employee_code == employee_code))
    if employee is None:
        raise ValueError("Employee not found")
    return employee


@router.post(
    "/records",
    response_model=ErpSyncResult,
    summary="Sync processed ERP attendance records",
    description="Stores ERP-calculated daily attendance. Send one record per employee/date. Re-sending the same erp_record_id is idempotent.",
    dependencies=[Depends(require_erp_scope("attendance:write"))],
)
async def sync_records(
    records: list[ErpAttendanceRecordCreate],
    session: AsyncSession = Depends(get_async_session),
) -> ErpSyncResult:
    result = ErpSyncResult()
    for item in records:
        try:
            employee = await _employee(session, item.employee_id, item.employee_code)
            record = await session.scalar(
                select(AttendanceRecord).where(AttendanceRecord.erp_record_id == item.erp_record_id)
            )
            if record is not None:
                result.duplicates.append({"erp_record_id": item.erp_record_id, "id": record.id})
                continue
            record = await session.scalar(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.attendance_date == item.attendance_date,
                )
            )
            if record is None:
                record = AttendanceRecord(employee_id=employee.id, attendance_date=item.attendance_date)
                session.add(record)
            record.status = item.status.upper()
            if item.shift_id is not None:
                shift = await session.get(Shift, item.shift_id)
                if shift is None:
                    raise ValueError(f"Shift {item.shift_id} not found")
                record.shift_id = shift.id
            else:
                record.shift_id = None
            record.punch_in = item.punch_in
            record.punch_out = item.punch_out
            record.worked_minutes = item.worked_minutes
            record.overtime_minutes = item.overtime_minutes
            record.late_minutes = item.late_minutes
            record.early_exit_minutes = item.early_exit_minutes
            record.source = "ERP"
            record.erp_record_id = item.erp_record_id
            record.sync_status = "ERP_CONFIRMED"
            record.last_synced_at = now_ist()
            await session.flush()
            result.accepted.append({"erp_record_id": item.erp_record_id, "id": record.id})
            await session.commit()
        except Exception as exc:
            await session.rollback()
            result.failed.append({"erp_record_id": item.erp_record_id, "error": str(exc)})
    await session.commit()
    return result


@router.post(
    "/records/bulk",
    response_model=ErpSyncResult,
    summary="Bulk sync ERP attendance records",
    description=(
        "Synchronizes daily processed attendance for multiple employees and dates. "
        "Records may represent past, current, or planned attendance. Each item is "
        "resolved by employee_code or employee_id and erp_record_id makes retries idempotent."
    ),
    dependencies=[Depends(require_erp_scope("attendance:write"))],
)
async def sync_records_bulk(
    payload: ErpAttendanceRecordBulkCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ErpSyncResult:
    return await sync_records(payload.records, session)
