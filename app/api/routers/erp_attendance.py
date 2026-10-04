"""ERP-owned processed attendance synchronization."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.erp_auth import require_erp_scope
from db.models import AttendanceRecord, Employee, Shift, now_ist
from schemas.attendance import ErpAttendanceRecordBulkCreate, ErpAttendanceRecordCreate, ErpSyncResult

router = APIRouter(prefix="/integrations/erp/attendance", tags=["erp-attendance"])


def _resolved_employee_id(item: ErpAttendanceRecordCreate, ids: set[int], codes: dict[str, int]) -> int | None:
    if item.employee_id in ids:
        return item.employee_id
    return codes.get(item.employee_code)


async def sync_records(
    records: list[ErpAttendanceRecordCreate],
    session: AsyncSession = Depends(get_async_session),
) -> ErpSyncResult:
    result = ErpSyncResult()
    for start in range(0, len(records), 500):
        chunk = records[start:start + 500]
        requested_ids = {item.employee_id for item in chunk if item.employee_id is not None}
        requested_codes = {item.employee_code for item in chunk if item.employee_code}
        employee_ids = set(await session.scalars(select(Employee.id).where(Employee.id.in_(requested_ids))))
        employee_codes = dict((await session.execute(
            select(Employee.employee_code, Employee.id).where(Employee.employee_code.in_(requested_codes))
        )).all())

        shift_ids = set(await session.scalars(select(Shift.id).where(
            Shift.id.in_({item.shift_id for item in chunk if item.shift_id is not None})
        )))
        event_ids = {item.erp_record_id for item in chunk}
        event_rows = (await session.execute(select(
            AttendanceRecord.id, AttendanceRecord.erp_record_id,
        ).where(AttendanceRecord.erp_record_id.in_(event_ids)))).all()
        event_to_id = {erp_id: record_id for record_id, erp_id in event_rows}
        record_event = {record_id: erp_id for record_id, erp_id in event_rows}
        date_keys = {
            (employee_id, item.attendance_date)
            for item in chunk if (employee_id := _resolved_employee_id(item, employee_ids, employee_codes)) is not None
        }
        date_rows = (await session.execute(select(
            AttendanceRecord.id, AttendanceRecord.employee_id,
            AttendanceRecord.attendance_date, AttendanceRecord.erp_record_id,
        ).where(tuple_(AttendanceRecord.employee_id, AttendanceRecord.attendance_date).in_(date_keys)))).all()
        date_to_id = {(employee_id, day): record_id for record_id, employee_id, day, _ in date_rows}
        record_event.update({record_id: erp_id for record_id, _, _, erp_id in date_rows})

        for item in chunk:
            try:
                employee_id = _resolved_employee_id(item, employee_ids, employee_codes)
                if employee_id is None:
                    raise ValueError("Employee not found")
                if duplicate_id := event_to_id.get(item.erp_record_id):
                    result.duplicates.append({"erp_record_id": item.erp_record_id, "id": duplicate_id})
                    continue
                key = (employee_id, item.attendance_date)
                record_id = date_to_id.get(key)
                record = await session.get(AttendanceRecord, record_id) if record_id is not None else None
                if record is None:
                    record = AttendanceRecord(employee_id=employee_id, attendance_date=item.attendance_date)
                    session.add(record)
                record.status = item.status.upper()
                if item.shift_id is not None and item.shift_id not in shift_ids:
                    raise ValueError(f"Shift {item.shift_id} not found")
                record.shift_id = item.shift_id
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
                await session.commit()
                previous_event = record_event.get(record.id)
                if previous_event:
                    event_to_id.pop(previous_event, None)
                event_to_id[item.erp_record_id] = record.id
                record_event[record.id] = item.erp_record_id
                date_to_id[key] = record.id
                result.accepted.append({"erp_record_id": item.erp_record_id, "id": record.id})
            except Exception as exc:
                await session.rollback()
                result.failed.append({"erp_record_id": item.erp_record_id, "error": str(exc)})
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
    """Sync ERP-calculated daily records; retries are idempotent by erp_record_id."""
    return await sync_records(payload.records, session)
