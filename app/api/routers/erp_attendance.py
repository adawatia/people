"""ERP-owned processed attendance synchronization.

Identity rules (see ``docs/erp-integration.md``):

* The ERP business key is ``erp_record_id``. It identifies one processed
  attendance record for its whole life.
* HRMS also enforces one row per employee per date
  (``uq_attendance_employee_date``). An ERP record id therefore may never move
  to a different employee/date, and a second ERP record id may never silently
  replace the record a different id already owns.
* A row that HRMS created itself (leave approval, manual attendance) has no ERP
  id; ERP adoption of that row is the normal path and is audited.
* Same id + same values = duplicate (no write). Same id + different values = a
  legitimate correction (update, audited). Different id for an occupied
  employee/date = permanent ``ATTENDANCE_RECORD_CONFLICT``.

Concurrency is handled by one advisory-lock statement per chunk (same key space
as ``core.erp_sync``) with the unique constraints as the final backstop. Items
are isolated in savepoints and committed once per chunk, so partial success is
preserved without one commit per row.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import add_audit_event
from core.database import get_async_session
from core.erp_auth import ErpPrincipal, require_erp_scope
from core.erp_batch import (
    ErpBatchResult,
    ErpItemError,
    apply_batch_status,
    classify_erp_error,
    log_erp_item_failure,
    new_batch,
    record_batch,
    resolve_batch_id,
)
from core.erp_sync import acquire_erp_upsert_locks
from db.models import AttendanceRecord, Employee, Shift, now_ist
from schemas.attendance import ErpAttendanceRecordBulkCreate, ErpAttendanceRecordCreate

router = APIRouter(prefix="/integrations/erp/attendance", tags=["erp-attendance"])

CHUNK_SIZE = 500
TRACKED_FIELDS = (
    "status",
    "punch_in",
    "punch_out",
    "worked_minutes",
    "overtime_minutes",
    "late_minutes",
    "early_exit_minutes",
)


def _resolved_employee_id(item: ErpAttendanceRecordCreate, ids: set[int], codes: dict[str, int]) -> int | None:
    if item.employee_id in ids:
        return item.employee_id
    return codes.get(item.employee_code)


def _values(item: ErpAttendanceRecordCreate) -> dict:
    values = {field: getattr(item, field) for field in TRACKED_FIELDS}
    values["status"] = item.status.upper()
    return values


def _diff(
    record: AttendanceRecord, values: dict, shift_id: int | None, include_shift: bool
) -> dict[str, dict[str, object]]:
    changes: dict[str, dict[str, object]] = {}
    for field, new_value in values.items():
        old_value = getattr(record, field)
        if old_value != new_value:
            changes[field] = {"old": old_value, "new": new_value}
    if include_shift and record.shift_id != shift_id:
        changes["shift_id"] = {"old": record.shift_id, "new": shift_id}
    return changes


def _apply(record: AttendanceRecord, item: ErpAttendanceRecordCreate, values: dict, *, set_shift: bool) -> None:
    for field, new_value in values.items():
        setattr(record, field, new_value)
    if set_shift:
        record.shift_id = item.shift_id
    record.source = "ERP"
    record.erp_record_id = item.erp_record_id
    record.sync_status = "ERP_CONFIRMED"
    record.last_synced_at = now_ist()


async def _apply_item(
    session: AsyncSession,
    item: ErpAttendanceRecordCreate,
    *,
    employee_id: int,
    shift_ids: set[int],
    events: dict[str, AttendanceRecord],
    by_date: dict[tuple[int, date], AttendanceRecord],
    batch_id: str,
) -> tuple[str, int]:
    """Return ``(status, record_id)`` where status is accepted or duplicate."""
    values = _values(item)
    set_shift = "shift_id" in item.model_fields_set
    if set_shift and item.shift_id is not None and item.shift_id not in shift_ids:
        raise ErpItemError("SHIFT_NOT_FOUND", "Shift not found", retryable=False)

    existing = events.get(item.erp_record_id)
    if existing is not None:
        if existing.employee_id != employee_id or existing.attendance_date != item.attendance_date:
            raise ErpItemError(
                "ERP_RECORD_ID_CONFLICT",
                "This erp_record_id already identifies an attendance record for another employee or date",
            )
        changes = _diff(existing, values, item.shift_id, set_shift)
        if not changes:
            return "duplicate", existing.id
        add_audit_event(
            session,
            actor=None,
            action="ERP_ATTENDANCE_CORRECTED",
            entity_type="attendance_record",
            entity_id=str(existing.id),
            filters={"erp_batch_id": batch_id, "erp_record_id": item.erp_record_id, "changes": changes},
        )
        _apply(existing, item, values, set_shift=set_shift)
        return "accepted", existing.id

    owner = by_date.get((employee_id, item.attendance_date))
    if owner is not None:
        if owner.erp_record_id and owner.erp_record_id != item.erp_record_id:
            # Fail closed: rebinding the row would strand the other ERP record.
            raise ErpItemError(
                "ATTENDANCE_RECORD_CONFLICT",
                f"This employee and date already belong to ERP record {owner.erp_record_id!r}",
            )
        previous_source = owner.source
        changes = _diff(owner, values, item.shift_id, set_shift)
        add_audit_event(
            session,
            actor=None,
            action="ERP_ATTENDANCE_ADOPTED" if owner.erp_record_id is None else "ERP_ATTENDANCE_CORRECTED",
            entity_type="attendance_record",
            entity_id=str(owner.id),
            filters={
                "erp_batch_id": batch_id,
                "erp_record_id": item.erp_record_id,
                "previous_source": previous_source,
                "changes": changes,
            },
        )
        _apply(owner, item, values, set_shift=set_shift)
        events[item.erp_record_id] = owner
        return "accepted", owner.id

    record = AttendanceRecord(employee_id=employee_id, attendance_date=item.attendance_date)
    _apply(record, item, values, set_shift=set_shift)
    session.add(record)
    # Flush so the id exists for the item result and for later items in the chunk.
    await session.flush()
    events[item.erp_record_id] = record
    by_date[(employee_id, item.attendance_date)] = record
    return "accepted", record.id


async def _classify_integrity_error(
    session: AsyncSession, item: ErpAttendanceRecordCreate, employee_id: int
) -> tuple[str, int]:
    """Resolve a lost race into duplicate vs conflict after a savepoint rollback."""
    existing = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.erp_record_id == item.erp_record_id)
    )
    if existing is not None:
        if existing.employee_id == employee_id and existing.attendance_date == item.attendance_date:
            return "duplicate", existing.id
        raise ErpItemError(
            "ERP_RECORD_ID_CONFLICT",
            "This erp_record_id already identifies an attendance record for another employee or date",
        )
    raise ErpItemError(
        "ATTENDANCE_RECORD_CONFLICT",
        "Another record was created for this employee and date concurrently; re-read before retrying",
    )


async def sync_records(
    records: list[ErpAttendanceRecordCreate],
    session: AsyncSession = Depends(get_async_session),
    *,
    batch_id: str | None = None,
    client_id: str | None = None,
) -> ErpBatchResult:
    """Sync ERP-calculated daily records; retries are idempotent by erp_record_id."""
    result = new_batch("attendance.records.bulk", batch_id or uuid.uuid4().hex, len(records))
    for start in range(0, len(records), CHUNK_SIZE):
        chunk = records[start : start + CHUNK_SIZE]
        requested_ids = {item.employee_id for item in chunk if item.employee_id is not None}
        requested_codes = {item.employee_code for item in chunk if item.employee_code}
        employee_ids = (
            set(await session.scalars(select(Employee.id).where(Employee.id.in_(requested_ids))))
            if requested_ids
            else set()
        )
        employee_codes = (
            dict(
                (
                    await session.execute(
                        select(Employee.employee_code, Employee.id).where(Employee.employee_code.in_(requested_codes))
                    )
                ).all()
            )
            if requested_codes
            else {}
        )
        chunk_shift_ids = {item.shift_id for item in chunk if item.shift_id is not None}
        shift_ids = (
            set(await session.scalars(select(Shift.id).where(Shift.id.in_(chunk_shift_ids))))
            if chunk_shift_ids
            else set()
        )
        chunk_record_ids = {item.erp_record_id for item in chunk}
        event_rows = (
            (
                await session.execute(
                    select(AttendanceRecord).where(
                        AttendanceRecord.erp_record_id.in_(chunk_record_ids)
                    )
                )
            ).scalars()
            if chunk_record_ids
            else []
        )
        events = {row.erp_record_id: row for row in event_rows}
        date_keys = {
            (emp_id, item.attendance_date)
            for item in chunk
            if (emp_id := _resolved_employee_id(item, employee_ids, employee_codes)) is not None
        }
        date_rows = (
            (
                await session.execute(
                    select(AttendanceRecord).where(
                        AttendanceRecord.employee_id.in_({key[0] for key in date_keys}),
                        AttendanceRecord.attendance_date.in_({key[1] for key in date_keys}),
                    )
                )
            ).scalars()
            if date_keys
            else []
        )
        by_date: dict[tuple[int, date], AttendanceRecord] = {
            (row.employee_id, row.attendance_date): row for row in date_rows
        }

        # One statement locks every employee/date this chunk will touch; taking
        # them in sorted order keeps concurrent chunks from deadlocking.
        await acquire_erp_upsert_locks(
            session,
            "attendance",
            [f"{emp_id}:{day.isoformat()}" for emp_id, day in date_keys],
        )

        outcomes: list[tuple[str, str, int | None]] = []
        for item in chunk:
            employee_id = _resolved_employee_id(item, employee_ids, employee_codes)
            try:
                if employee_id is None:
                    raise ErpItemError("EMPLOYEE_NOT_FOUND", "Employee not found", retryable=False)
                async with session.begin_nested():
                    status, local_id = await _apply_item(
                        session,
                        item,
                        employee_id=employee_id,
                        shift_ids=shift_ids,
                        events=events,
                        by_date=by_date,
                        batch_id=result.batch_id,
                    )
                    await session.flush()
                outcomes.append((status, item.erp_record_id, local_id))
            except IntegrityError:
                try:
                    status, local_id = await _classify_integrity_error(session, item, employee_id)
                    outcomes.append((status, item.erp_record_id, local_id))
                except Exception as exc:
                    log_erp_item_failure(item.erp_record_id, exc, result.batch_id, result.endpoint)
                    code, message, retryable = classify_erp_error(exc)
                    result.add_failure(item.erp_record_id, code=code, message=message, retryable=retryable)
            except Exception as exc:
                log_erp_item_failure(item.erp_record_id, exc, result.batch_id, result.endpoint)
                code, message, retryable = classify_erp_error(exc)
                result.add_failure(item.erp_record_id, code=code, message=message, retryable=retryable)

        # Commit once per chunk and only then report its items as accepted.
        await session.commit()
        for status, key, local_id in outcomes:
            if status == "duplicate":
                result.add_duplicate(key, local_id)
            else:
                result.add_accepted(key, local_id)
    return result


@router.post(
    "/records/bulk",
    response_model=ErpBatchResult,
    summary="Bulk sync ERP attendance records",
    description=(
        "Synchronizes daily processed attendance for multiple employees and dates. "
        "`erp_record_id` is the record identity; replaying the same values reports "
        "`duplicate`, changed values are applied as an audited correction, and a "
        "different id for an occupied employee/date fails with "
        "`ATTENDANCE_RECORD_CONFLICT`. Items are committed per chunk of 500."
    ),
)
async def sync_records_bulk(
    response: Response,
    payload: ErpAttendanceRecordBulkCreate,
    batch_id: Annotated[str, Depends(resolve_batch_id)],
    principal: Annotated[ErpPrincipal, Depends(require_erp_scope("attendance:write"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ErpBatchResult:
    result = await sync_records(payload.records, session, batch_id=batch_id, client_id=principal.client_id)
    apply_batch_status(response, result)
    await record_batch(session, result, client_id=principal.client_id, http_status=response.status_code)
    await session.commit()
    return result
