"""ERP-owned overtime synchronization.

ERP owns the *source* overtime record: how many minutes were worked and which
attendance record they belong to. HRMS owns the approval decision, so an ERP
payload may only ever create a PENDING record with zero approved minutes —
anything else is rejected rather than silently overwriting an HRMS decision.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from db.models import AttendanceRecord, Employee, OvertimeRecord

router = APIRouter(prefix="/integrations/erp/overtime", tags=["erp-overtime"])

CHUNK_SIZE = 500


class ErpOvertimeRecord(BaseModel):
    erp_event_id: str
    employee_id: int | None = None
    employee_code: str | None = None
    attendance_record_id: int
    overtime_start: datetime | None = None
    overtime_end: datetime | None = None
    calculated_minutes: int = Field(ge=0)
    approved_minutes: int = Field(default=0, ge=0)
    status: str = "PENDING"


async def sync_overtime_bulk(
    records: list[ErpOvertimeRecord],
    session: AsyncSession = Depends(get_async_session),
    *,
    batch_id: str | None = None,
    client_id: str | None = None,
) -> ErpBatchResult:
    result = new_batch("overtime.records.bulk", batch_id or uuid.uuid4().hex, len(records))
    for start in range(0, len(records), CHUNK_SIZE):
        chunk = records[start : start + CHUNK_SIZE]
        requested_ids = {item.employee_id for item in chunk if item.employee_id is not None}
        requested_codes = {item.employee_code for item in chunk if item.employee_code}
        employee_ids = set(await session.scalars(select(Employee.id).where(Employee.id.in_(requested_ids))))
        employee_codes = dict(
            (
                await session.execute(
                    select(Employee.employee_code, Employee.id).where(Employee.employee_code.in_(requested_codes))
                )
            ).all()
        )
        attendance_owners = dict(
            (
                await session.execute(
                    select(AttendanceRecord.id, AttendanceRecord.employee_id).where(
                        AttendanceRecord.id.in_({item.attendance_record_id for item in chunk})
                    )
                )
            ).all()
        )
        existing_events = dict(
            (
                await session.execute(
                    select(OvertimeRecord.erp_event_id, OvertimeRecord.id).where(
                        OvertimeRecord.erp_event_id.in_({item.erp_event_id for item in chunk})
                    )
                )
            ).all()
        )

        outcomes: list[tuple[str, str, int | None]] = []
        for item in chunk:
            try:
                if existing_id := existing_events.get(item.erp_event_id):
                    outcomes.append(("duplicate", item.erp_event_id, existing_id))
                    continue
                employee_id = (
                    item.employee_id if item.employee_id in employee_ids else employee_codes.get(item.employee_code)
                )
                if employee_id is None or attendance_owners.get(item.attendance_record_id) != employee_id:
                    raise ErpItemError(
                        "OVERTIME_TARGET_NOT_FOUND",
                        "Employee or attendance record not found, or they do not match",
                    )
                if item.status.upper() != "PENDING":
                    raise ErpItemError(
                        "OVERTIME_STATUS_NOT_ERP_OWNED",
                        "ERP overtime must be PENDING; HRMS owns the approval decision",
                    )
                if item.approved_minutes != 0:
                    raise ErpItemError(
                        "OVERTIME_APPROVAL_NOT_ERP_OWNED",
                        "ERP overtime must have zero approved minutes; HRMS owns approval",
                    )
                if item.approved_minutes > item.calculated_minutes:
                    raise ErpItemError(
                        "OVERTIME_MINUTES_INVALID",
                        "approved_minutes cannot exceed calculated_minutes",
                    )
                async with session.begin_nested():
                    record = OvertimeRecord(
                        employee_id=employee_id,
                        attendance_record_id=item.attendance_record_id,
                        calculated_minutes=item.calculated_minutes,
                        approved_minutes=item.approved_minutes,
                        status=item.status.upper(),
                        erp_event_id=item.erp_event_id,
                        overtime_start=item.overtime_start,
                        overtime_end=item.overtime_end,
                        source="ERP",
                    )
                    session.add(record)
                    await session.flush()
                outcomes.append(("accepted", item.erp_event_id, record.id))
                existing_events[item.erp_event_id] = record.id
            except IntegrityError:
                # Two workers inserted the same event at once: the loser re-reads
                # and reports a duplicate instead of a failure.
                existing_id = await session.scalar(
                    select(OvertimeRecord.id).where(OvertimeRecord.erp_event_id == item.erp_event_id)
                )
                if existing_id:
                    outcomes.append(("duplicate", item.erp_event_id, existing_id))
                else:
                    result.add_failure(
                        item.erp_event_id,
                        code="CONFLICT",
                        message="Conflicts with existing overtime data",
                        retryable=False,
                    )
            except Exception as exc:
                log_erp_item_failure(item.erp_event_id, exc, result.batch_id, result.endpoint)
                code, message, retryable = classify_erp_error(exc)
                result.add_failure(item.erp_event_id, code=code, message=message, retryable=retryable)

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
    summary="Bulk sync ERP overtime records",
    description=(
        "Creates PENDING overtime records for HRMS approval. `erp_event_id` is the "
        "idempotency key: replaying an event reports `duplicate`. ERP may never set "
        "status or approved_minutes — those are HRMS-owned."
    ),
)
async def sync_overtime_bulk_endpoint(
    response: Response,
    records: Annotated[list[ErpOvertimeRecord], Body(max_length=5000)],
    batch_id: Annotated[str, Depends(resolve_batch_id)],
    principal: Annotated[ErpPrincipal, Depends(require_erp_scope("overtime:write"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ErpBatchResult:
    result = await sync_overtime_bulk(records, session, batch_id=batch_id, client_id=principal.client_id)
    apply_batch_status(response, result)
    await record_batch(session, result, client_id=principal.client_id, http_status=response.status_code)
    await session.commit()
    return result
