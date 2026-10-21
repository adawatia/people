"""Operational diagnostics and reconciliation for the ERP integration.

Two questions operations must be able to answer without reading source code:

* Is the integration healthy? ``GET /sync/status`` reports the pending event
  backlog and its age, the last delivery, per-entity batch history and whether
  replay protection is shared across workers.
* Does HRMS match ERP? The reconciliation endpoints compare an ERP-supplied
  snapshot against the local mirror and report discrepancies. They are dry-run
  by default: nothing is written until the operator passes ``apply=true``, and
  then only through the normal audited sync path.

Absence from a partial payload is never treated as a deletion. Reconciliation
only compares the explicit date window the caller supplies.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.erp_auth import ErpPrincipal, require_erp_scope
from core.erp_batch import ErpBatchResult, record_batch
from core.erp_nonce_store import get_global_nonce_store
from core.settings import get_settings
from db.models import AttendanceRecord, Employee, ErpOutboxEvent, ErpSyncBatch, LeaveBalance, LeaveType, now_ist
from routers.erp_attendance import sync_records
from routers.erp_leaves import ErpLeaveBalance, sync_leave_balances
from schemas.attendance import ErpAttendanceRecordCreate
from services.erp_outbox import LEAVE_ENTITY

router = APIRouter(prefix="/integrations/erp", tags=["erp-operations"])

MAX_RECONCILIATION_DAYS = 366

ATTENDANCE_FIELDS = (
    "status",
    "punch_in",
    "punch_out",
    "worked_minutes",
    "overtime_minutes",
    "late_minutes",
    "early_exit_minutes",
    "shift_id",
)


# ── Status ─────────────────────────────────────────────────────────────────────


class ErpBatchCounts(BaseModel):
    received: int = 0
    accepted: int = 0
    duplicate: int = 0
    failed: int = 0


class ErpEntityStatus(BaseModel):
    entity: str
    last_batch_at: datetime | None = None
    last_accepted_at: datetime | None = None
    last_error_code: str | None = None
    counts_last_24h: ErpBatchCounts = Field(default_factory=ErpBatchCounts)


class ErpFeedStatus(BaseModel):
    pending_events: int = 0
    oldest_pending_event_age_seconds: int | None = None
    last_delivery_at: datetime | None = None
    behind_schedule: bool = False


class ErpNonceStatus(BaseModel):
    backend: Literal["redis", "memory"]
    replay_protection_shared: bool


class ErpSyncStatus(BaseModel):
    generated_at: datetime
    stale_after_seconds: int
    feed: ErpFeedStatus
    entities: list[ErpEntityStatus] = Field(default_factory=list)
    nonce: ErpNonceStatus


@router.get(
    "/sync/status",
    response_model=ErpSyncStatus,
    summary="ERP integration health and backlog",
    description=(
        "Reports pending outbound events (count and oldest age), last delivery, "
        "per-entity batch results for the last 24 hours, and the replay-protection "
        "backend. Use this for alerting instead of scraping logs."
    ),
    dependencies=[Depends(require_erp_scope("sync:read"))],
)
async def get_sync_status(session: Annotated[AsyncSession, Depends(get_async_session)]) -> ErpSyncStatus:
    settings = get_settings()
    stale_after = settings.erp_sync_stale_after_seconds

    pending, oldest_created, last_delivery = (
        await session.execute(
            select(
                func.count(),
                func.min(ErpOutboxEvent.created_at),
                func.max(ErpOutboxEvent.last_delivered_at),
            ).where(
                ErpOutboxEvent.entity_type == LEAVE_ENTITY,
                ErpOutboxEvent.acknowledged_at.is_(None),
            )
        )
    ).one()
    now = now_ist()
    oldest_age = int((now - oldest_created).total_seconds()) if oldest_created else None

    since = now - timedelta(hours=24)
    batches = list(
        (
            await session.execute(
                select(ErpSyncBatch).where(ErpSyncBatch.created_at >= since).order_by(ErpSyncBatch.created_at.desc())
            )
        ).scalars()
    )
    entities: dict[str, ErpEntityStatus] = {}
    for batch in batches:
        entity = batch.endpoint.split(".")[0]
        status = entities.setdefault(entity, ErpEntityStatus(entity=entity))
        counts = status.counts_last_24h
        counts.received += batch.received_count
        counts.accepted += batch.accepted_count
        counts.duplicate += batch.duplicate_count
        counts.failed += batch.failed_count
        if status.last_batch_at is None:
            status.last_batch_at = batch.created_at
            status.last_error_code = batch.last_error_code
        if status.last_accepted_at is None and batch.accepted_count:
            status.last_accepted_at = batch.created_at

    store = get_global_nonce_store()
    return ErpSyncStatus(
        generated_at=now,
        stale_after_seconds=stale_after,
        feed=ErpFeedStatus(
            pending_events=int(pending or 0),
            oldest_pending_event_age_seconds=oldest_age,
            last_delivery_at=last_delivery,
            behind_schedule=bool(oldest_age is not None and oldest_age > stale_after),
        ),
        entities=sorted(entities.values(), key=lambda item: item.entity),
        nonce=ErpNonceStatus(backend=store.backend, replay_protection_shared=store.is_shared),
    )


# ── Reconciliation ─────────────────────────────────────────────────────────────


class ReconcileDiscrepancy(BaseModel):
    kind: Literal[
        "missing_in_hrms",
        "missing_in_erp",
        "unlinked_hrms_record",
        "mismatched",
        "unknown_employee",
    ]
    erp_record_id: str | None = None
    employee_code: str | None = None
    attendance_date: date | None = None
    leave_code: str | None = None
    year: int | None = None
    fields: dict[str, dict[str, object]] = Field(default_factory=dict)


class ErpReconciliationResult(BaseModel):
    batch_id: str
    apply: bool
    from_date: date | None = None
    to_date: date | None = None
    compared_count: int = 0
    discrepancy_count: int = 0
    discrepancies: list[ReconcileDiscrepancy] = Field(default_factory=list)
    applied: ErpBatchResult | None = None


class AttendanceReconciliationRequest(BaseModel):
    from_date: date
    to_date: date
    records: list[ErpAttendanceRecordCreate] = Field(max_length=5000)
    apply: bool = False


def _validate_window(from_date: date, to_date: date) -> None:
    if to_date < from_date:
        raise HTTPException(status_code=422, detail="to_date must be on or after from_date")
    if (to_date - from_date).days > MAX_RECONCILIATION_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Reconciliation window must not exceed {MAX_RECONCILIATION_DAYS} days",
        )


@router.post(
    "/reconciliation/attendance",
    response_model=ErpReconciliationResult,
    summary="Compare ERP attendance against the HRMS mirror",
    description=(
        "Dry-run by default. Compares the supplied ERP snapshot inside the given "
        "date window and reports missing, unlinked, and field-level mismatches. "
        "`apply=true` then runs the normal audited attendance sync."
    ),
)
async def reconcile_attendance(
    request: AttendanceReconciliationRequest,
    principal: Annotated[ErpPrincipal, Depends(require_erp_scope("attendance:write"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ErpReconciliationResult:
    _validate_window(request.from_date, request.to_date)
    batch_id = uuid.uuid4().hex

    local_rows = list(
        (
            await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.attendance_date >= request.from_date,
                    AttendanceRecord.attendance_date <= request.to_date,
                )
            )
        ).scalars()
    )
    all_employee_ids = {item.employee_id for item in request.records if item.employee_id} | {
        row.employee_id for row in local_rows
    }
    employee_codes = (
        dict(
            (
                await session.execute(
                    select(Employee.id, Employee.employee_code).where(
                        Employee.id.in_(all_employee_ids)
                    )
                )
            ).all()
        )
        if all_employee_ids
        else {}
    )
    code_to_id = dict(
        (
            await session.execute(
                select(Employee.employee_code, Employee.id).where(
                    Employee.employee_code.in_({item.employee_code for item in request.records if item.employee_code})
                )
            )
        ).all()
    )
    by_erp_id = {row.erp_record_id: row for row in local_rows if row.erp_record_id}
    by_key = {(row.employee_id, row.attendance_date): row for row in local_rows}

    discrepancies: list[ReconcileDiscrepancy] = []
    seen_ids: set[str] = set()
    for item in request.records:
        employee_id = item.employee_id if item.employee_id in employee_codes else code_to_id.get(item.employee_code)
        if employee_id is None:
            discrepancies.append(
                ReconcileDiscrepancy(
                    kind="unknown_employee",
                    erp_record_id=item.erp_record_id,
                    employee_code=item.employee_code,
                    attendance_date=item.attendance_date,
                )
            )
            continue
        seen_ids.add(item.erp_record_id)
        row = by_erp_id.get(item.erp_record_id)
        if row is None:
            unlinked = by_key.get((employee_id, item.attendance_date))
            kind: Literal["missing_in_hrms", "unlinked_hrms_record"] = (
                "unlinked_hrms_record" if unlinked is not None else "missing_in_hrms"
            )
            discrepancies.append(
                ReconcileDiscrepancy(
                    kind=kind,
                    erp_record_id=item.erp_record_id,
                    employee_code=employee_codes.get(employee_id, item.employee_code),
                    attendance_date=item.attendance_date,
                    fields=(
                        {"erp_record_id": {"hrms": unlinked.erp_record_id, "erp": item.erp_record_id}}
                        if unlinked is not None
                        else {}
                    ),
                )
            )
            continue
        expected = {
            "status": item.status.upper(),
            "punch_in": item.punch_in,
            "punch_out": item.punch_out,
            "worked_minutes": item.worked_minutes,
            "overtime_minutes": item.overtime_minutes,
            "late_minutes": item.late_minutes,
            "early_exit_minutes": item.early_exit_minutes,
        }
        if "shift_id" in item.model_fields_set:
            expected["shift_id"] = item.shift_id
        fields = {
            field: {"hrms": getattr(row, field), "erp": value}
            for field, value in expected.items()
            if getattr(row, field) != value
        }
        if fields:
            discrepancies.append(
                ReconcileDiscrepancy(
                    kind="mismatched",
                    erp_record_id=item.erp_record_id,
                    employee_code=employee_codes.get(employee_id, item.employee_code),
                    attendance_date=item.attendance_date,
                    fields=fields,
                )
            )

    for row in local_rows:
        if row.source != "ERP" or not row.erp_record_id:
            continue
        if row.erp_record_id not in seen_ids:
            discrepancies.append(
                ReconcileDiscrepancy(
                    kind="missing_in_erp",
                    erp_record_id=row.erp_record_id,
                    employee_code=employee_codes.get(row.employee_id),
                    attendance_date=row.attendance_date,
                )
            )

    result = ErpReconciliationResult(
        batch_id=batch_id,
        apply=request.apply,
        from_date=request.from_date,
        to_date=request.to_date,
        compared_count=len(request.records),
        discrepancy_count=len(discrepancies),
        discrepancies=discrepancies,
    )
    if request.apply:
        applied = await sync_records(
            request.records, session, batch_id=batch_id, client_id=principal.client_id
        )
        await record_batch(session, applied, client_id=principal.client_id)
        await session.commit()
        result.applied = applied
    return result


class LeaveBalanceReconciliationRequest(BaseModel):
    balances: list[ErpLeaveBalance] = Field(max_length=5000)
    apply: bool = False


@router.post(
    "/reconciliation/leave-balances",
    response_model=ErpReconciliationResult,
    summary="Compare ERP leave balances against the HRMS mirror",
    description=(
        "Dry-run by default. Reports balances missing in HRMS and field-level "
        "differences. `apply=true` runs the normal audited balance sync. A balance "
        "ERP does not mention is not treated as zero or deleted."
    ),
)
async def reconcile_leave_balances(
    request: LeaveBalanceReconciliationRequest,
    principal: Annotated[ErpPrincipal, Depends(require_erp_scope("leaves:write"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ErpReconciliationResult:
    batch_id = uuid.uuid4().hex
    discrepancies: list[ReconcileDiscrepancy] = []
    for item in request.balances:
        employee = await session.get(Employee, item.employee_id) if item.employee_id else None
        if employee is None and item.employee_code:
            employee = await session.scalar(select(Employee).where(Employee.employee_code == item.employee_code))
        leave_type = await session.scalar(
            select(LeaveType).where(func.upper(LeaveType.code) == item.leave_code.strip().upper())
        )
        if employee is None or leave_type is None:
            discrepancies.append(
                ReconcileDiscrepancy(
                    kind="unknown_employee" if employee is None else "missing_in_hrms",
                    employee_code=item.employee_code,
                    leave_code=item.leave_code,
                    year=item.year,
                )
            )
            continue
        balance = await session.scalar(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee.id,
                LeaveBalance.leave_type_id == leave_type.id,
                LeaveBalance.year == item.year,
            )
        )
        if balance is None:
            discrepancies.append(
                ReconcileDiscrepancy(
                    kind="missing_in_hrms",
                    employee_code=employee.employee_code,
                    leave_code=leave_type.code,
                    year=item.year,
                )
            )
            continue
        expected = {
            "allocated": float(balance.allocated) - item.allocated,
            "used": float(balance.used) - item.used,
            "pending": float(balance.pending) - item.pending,
        }
        fields = {
            "allocated": {"hrms": float(balance.allocated), "erp": item.allocated},
            "used": {"hrms": float(balance.used), "erp": item.used},
            "pending": {"hrms": float(balance.pending), "erp": item.pending},
        }
        if any(abs(delta) > 1e-9 for delta in expected.values()):
            discrepancies.append(
                ReconcileDiscrepancy(
                    kind="mismatched",
                    employee_code=employee.employee_code,
                    leave_code=leave_type.code,
                    year=item.year,
                    fields=fields,
                )
            )

    result = ErpReconciliationResult(
        batch_id=batch_id,
        apply=request.apply,
        compared_count=len(request.balances),
        discrepancy_count=len(discrepancies),
        discrepancies=discrepancies,
    )
    if request.apply:
        applied = await sync_leave_balances(
            request.balances, session, batch_id=batch_id, client_id=principal.client_id
        )
        await record_batch(session, applied, client_id=principal.client_id)
        await session.commit()
        result.applied = applied
    return result


class ErpPendingEventItem(BaseModel):
    event_id: str
    sequence: int
    entity_id: int
    event_type: str
    created_at: datetime
    delivery_attempts: int
    last_delivered_at: datetime | None = None


class ErpPendingEventsResponse(BaseModel):
    items: list[ErpPendingEventItem] = Field(default_factory=list)


@router.get(
    "/sync/pending-events",
    response_model=ErpPendingEventsResponse,
    summary="Pending outbound events awaiting ERP acknowledgement",
    dependencies=[Depends(require_erp_scope("sync:read"))],
)
async def list_pending_events(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    session: Annotated[AsyncSession, Depends(get_async_session)] = None,
) -> ErpPendingEventsResponse:
    rows = list(
        (
            await session.execute(
                select(ErpOutboxEvent)
                .where(ErpOutboxEvent.entity_type == LEAVE_ENTITY, ErpOutboxEvent.acknowledged_at.is_(None))
                .order_by(ErpOutboxEvent.sequence)
                .limit(limit)
            )
        ).scalars()
    )
    return ErpPendingEventsResponse(
        items=[
            ErpPendingEventItem(
                event_id=row.event_id,
                sequence=row.sequence,
                entity_id=row.entity_id,
                event_type=row.event_type,
                created_at=row.created_at,
                delivery_attempts=row.delivery_attempts,
                last_delivered_at=row.last_delivered_at,
            )
            for row in rows
        ]
    )
