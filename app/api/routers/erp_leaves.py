"""ERP leave status change feed, acknowledgements, and leave master data.

Delivery contract (see ``docs/erp-integration.md``):

1. HRMS stages an immutable outbox row in the same transaction as the leave
   decision. Nothing is delivered by "updating a flag on the application".
2. ERP polls ``GET /changes`` with the ``next_cursor`` it received last time.
   Rows are ordered by the outbox ``sequence``, which is monotonic and stable,
   so events sharing a timestamp cannot be skipped.
3. Every returned event stays pending until ERP acknowledges it. Fetching never
   acknowledges anything.
4. ``POST /changes/ack`` is idempotent: re-acknowledging returns
   ``already_acknowledged`` instead of an error, unknown ids are reported
   separately, and an acknowledgement never hides a newer event for the same
   application.

``since`` is still accepted for one transition window. It is mapped to a
sequence boundary using ``created_at < since`` so equal timestamps are
redelivered rather than lost; clients should move to ``cursor``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import add_audit_event
from core.database import get_async_session
from core.erp_auth import ErpPrincipal, require_erp_scope
from core.erp_batch import (
    ErpBatchResult,
    apply_batch_status,
    classify_erp_error,
    log_erp_item_failure,
    new_batch,
    record_batch,
    resolve_batch_id,
)
from db.models import Employee, ErpOutboxEvent, LeaveApplication, LeaveBalance, LeaveType, now_ist
from schemas.leaves import LeavePeriodCreate, LeavePeriodRead, LeaveTypeCreate, LeaveTypeRead, LeaveTypeUpdate
from services.erp_outbox import LEAVE_ENTITY, pending_event_count
from services.leave_service import LeaveService

logger = logging.getLogger("hrms.erp")

router = APIRouter(prefix="/integrations/erp/leaves", tags=["erp-leaves"])

MAX_ACK_EVENTS = 500


# ── Wire models ────────────────────────────────────────────────────────────────


class ErpLeaveBalance(BaseModel):
    employee_id: int | None = None
    employee_code: str | None = None
    leave_code: str
    year: int = Field(ge=2000, le=2100)
    allocated: float = Field(default=0, ge=0)
    used: float = Field(default=0, ge=0)
    pending: float = Field(default=0, ge=0)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "employee_code": "EMP001",
                    "leave_code": "CL",
                    "year": 2026,
                    "allocated": 12,
                    "used": 2,
                    "pending": 0,
                }
            ]
        }
    }


class ErpLeaveChange(BaseModel):
    event_id: str
    sequence: int
    event_type: str
    leave_id: int
    employee_code: str | None = None
    leave_code: str | None = None
    from_date: date
    to_date: date
    days: float
    status: str
    reason: str | None = None
    rejection_reason: str | None = None
    approved_at: datetime | None = None


class ErpLeaveChangesResponse(BaseModel):
    items: list[ErpLeaveChange] = Field(default_factory=list)
    has_more: bool
    next_cursor: str | None = None
    pending_count: int = 0


class ErpLeaveAckRequest(BaseModel):
    event_ids: list[str] = Field(max_length=MAX_ACK_EVENTS)
    batch_id: str | None = None

    model_config = ConfigDict(
        json_schema_extra={"example": {"event_ids": ["LEAVE-42-APPROVED"], "batch_id": "ack-2026-10-21-01"}}
    )


class ErpLeaveChangesAcknowledgement(BaseModel):
    batch_id: str
    acknowledged: list[str] = Field(default_factory=list)
    already_acknowledged: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    pending_remaining: int = 0


# ── Feed ───────────────────────────────────────────────────────────────────────


def _parse_cursor(cursor: str | None) -> int:
    if cursor in (None, ""):
        return 0
    try:
        value = int(cursor)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="cursor must be the next_cursor value returned by this endpoint",
        ) from exc
    if value < 0:
        raise HTTPException(status_code=422, detail="cursor must not be negative")
    return value


def _payload_date(value: object, fallback: date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback


def _payload_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _payload_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _to_change(event: ErpOutboxEvent) -> ErpLeaveChange:
    """Render an outbox row without letting a bad payload stall the feed."""
    payload = event.payload or {}
    fallback_date = event.created_at.date() if event.created_at else now_ist().date()
    return ErpLeaveChange(
        event_id=event.event_id,
        sequence=event.sequence,
        event_type=event.event_type,
        leave_id=int(payload.get("leave_id") or event.entity_id),
        employee_code=payload.get("employee_code"),
        leave_code=payload.get("leave_code"),
        from_date=_payload_date(payload.get("from_date"), fallback_date),
        to_date=_payload_date(payload.get("to_date"), fallback_date),
        days=_payload_float(payload.get("days")),
        status=str(payload.get("status") or event.event_type),
        reason=payload.get("reason"),
        rejection_reason=payload.get("rejection_reason"),
        approved_at=_payload_datetime(payload.get("approved_at")),
    )


@router.get(
    "/changes",
    response_model=ErpLeaveChangesResponse,
    summary="Pull leave outcomes produced by HRMS",
    description=(
        "Returns unacknowledged leave events in stable sequence order. Pass the "
        "previous response's `next_cursor`. Duplicate delivery is expected until "
        "the event is acknowledged; fetching does not acknowledge."
    ),
    dependencies=[Depends(require_erp_scope("leaves:read"))],
)
async def get_leave_changes(
    cursor: Annotated[str | None, Query(description="Opaque cursor from the previous response")] = None,
    since: Annotated[
        datetime | None,
        Query(
            deprecated=True,
            description="Legacy timestamp cursor. Prefer `cursor`; equal timestamps are redelivered.",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: Annotated[AsyncSession, Depends(get_async_session)] = None,
) -> ErpLeaveChangesResponse:
    cursor_value = _parse_cursor(cursor)
    if cursor is None and since is not None:
        # Legacy clients advance a timestamp. Using `created_at < since` as the
        # boundary deliberately re-delivers events created at exactly `since`
        # instead of skipping them: at-least-once beats silent loss.
        boundary = await session.scalar(
            select(func.max(ErpOutboxEvent.sequence)).where(ErpOutboxEvent.created_at < since)
        )
        cursor_value = int(boundary or 0)

    rows = list(
        (
            await session.execute(
                select(ErpOutboxEvent)
                .where(
                    ErpOutboxEvent.entity_type == LEAVE_ENTITY,
                    ErpOutboxEvent.acknowledged_at.is_(None),
                    ErpOutboxEvent.sequence > cursor_value,
                )
                .order_by(ErpOutboxEvent.sequence)
                .limit(limit + 1)
            )
        ).scalars()
    )
    has_more = len(rows) > limit
    page = rows[:limit]

    if page:
        # Delivery accounting only: this must never acknowledge an event.
        await session.execute(
            update(ErpOutboxEvent)
            .where(ErpOutboxEvent.sequence.in_([row.sequence for row in page]))
            .values(
                delivery_attempts=ErpOutboxEvent.delivery_attempts + 1,
                last_delivered_at=now_ist(),
            )
        )
        await session.commit()

    next_cursor = str(page[-1].sequence) if page else (str(cursor_value) if cursor_value else None)
    return ErpLeaveChangesResponse(
        items=[_to_change(row) for row in page],
        has_more=has_more,
        next_cursor=next_cursor,
        pending_count=await pending_event_count(session),
    )


# ── Acknowledgement ────────────────────────────────────────────────────────────


@router.post(
    "/changes/ack",
    response_model=ErpLeaveChangesAcknowledgement,
    summary="Acknowledge processed leave events",
    description=(
        "Acknowledges events ERP has successfully processed. Idempotent: ids that "
        "were already acknowledged are reported in `already_acknowledged`, ids "
        "that do not belong to this feed in `unknown`. A bare list of ids is still "
        "accepted for existing clients."
    ),
)
async def acknowledge_leave_changes(
    payload: Annotated[ErpLeaveAckRequest | list[str], Body()],
    batch_id: Annotated[str, Depends(resolve_batch_id)],
    principal: Annotated[ErpPrincipal, Depends(require_erp_scope("leaves:write"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ErpLeaveChangesAcknowledgement:
    if isinstance(payload, list):
        requested = payload
    else:
        requested = payload.event_ids
        batch_id = payload.batch_id or batch_id

    # Duplicate ids in one request are a client bug, not an error: collapse them.
    unique_ids = list(dict.fromkeys(item.strip() for item in requested if item and item.strip()))
    if len(unique_ids) > MAX_ACK_EVENTS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_ACK_EVENTS} event ids per acknowledgement")

    if not unique_ids:
        return ErpLeaveChangesAcknowledgement(batch_id=batch_id, pending_remaining=await pending_event_count(session))

    rows = list(
        (
            await session.execute(
                select(ErpOutboxEvent)
                .where(
                    ErpOutboxEvent.event_id.in_(unique_ids),
                    ErpOutboxEvent.entity_type == LEAVE_ENTITY,
                )
                .with_for_update()
            )
        ).scalars()
    )
    by_id = {row.event_id: row for row in rows}
    now = now_ist()
    newly: list[str] = []
    already: list[str] = []
    for event_id in unique_ids:
        row = by_id.get(event_id)
        if row is None:
            continue
        if row.acknowledged_at is not None:
            already.append(event_id)
            continue
        row.acknowledged_at = now
        row.acknowledged_by = principal.client_id
        newly.append(event_id)
    unknown = [event_id for event_id in unique_ids if event_id not in by_id]

    entity_ids = {by_id[event_id].entity_id for event_id in newly}
    if entity_ids:
        still_pending = set(
            await session.scalars(
                select(ErpOutboxEvent.entity_id).where(
                    ErpOutboxEvent.entity_type == LEAVE_ENTITY,
                    ErpOutboxEvent.acknowledged_at.is_(None),
                    ErpOutboxEvent.entity_id.in_(entity_ids),
                )
            )
        )
        # Only mirror ACKNOWLEDGED when this was the application's last pending
        # event; otherwise a newer decision would be invisible to the ERP.
        finalised = entity_ids - still_pending
        if finalised:
            await session.execute(
                update(LeaveApplication)
                .where(LeaveApplication.id.in_(finalised))
                .values(erp_sync_status="ACKNOWLEDGED", erp_synced_at=now)
            )

    add_audit_event(
        session,
        actor=None,
        action="ERP_LEAVE_EVENTS_ACKNOWLEDGED",
        entity_type="erp_batch",
        entity_id=batch_id,
        filters={
            "acknowledged": len(newly),
            "already_acknowledged": len(already),
            "unknown": len(unknown),
        },
    )
    pending_remaining = await pending_event_count(session)
    await session.commit()
    return ErpLeaveChangesAcknowledgement(
        batch_id=batch_id,
        acknowledged=newly,
        already_acknowledged=already,
        unknown=unknown,
        pending_remaining=pending_remaining,
    )


# ── Leave balances (ERP-owned mirror) ──────────────────────────────────────────


async def sync_leave_balances(
    balances: list[ErpLeaveBalance],
    session: AsyncSession,
    *,
    batch_id: str = "",
    client_id: str | None = None,
) -> ErpBatchResult:
    """Upsert ERP-authoritative balances, one savepoint per balance."""
    result = new_batch("leaves.balances.bulk", batch_id or "internal", len(balances))
    for item in balances:
        key = f"{item.employee_code or item.employee_id}:{item.leave_code}:{item.year}"
        try:
            unchanged = False
            async with session.begin_nested():
                if any(
                    Decimal(str(value)) % Decimal("0.5") for value in (item.allocated, item.used, item.pending)
                ):
                    raise HTTPException(status_code=422, detail="Leave balances must use half-day increments")
                employee = await session.get(Employee, item.employee_id) if item.employee_id else None
                if employee is None and item.employee_code:
                    employee = await session.scalar(
                        select(Employee).where(Employee.employee_code == item.employee_code)
                    )
                if employee is None:
                    raise HTTPException(status_code=404, detail="Employee not found for this leave balance")
                # ERP leave codes are matched case-insensitively; the stored code
                # keeps the organisation's own casing.
                leave_type = await session.scalar(
                    select(LeaveType).where(func.upper(LeaveType.code) == item.leave_code.strip().upper())
                )
                if leave_type is None:
                    raise HTTPException(status_code=404, detail="Leave type code not found")
                balance = await session.scalar(
                    select(LeaveBalance).where(
                        LeaveBalance.employee_id == employee.id,
                        LeaveBalance.leave_type_id == leave_type.id,
                        LeaveBalance.year == item.year,
                    )
                )
                values = (
                    Decimal(str(item.allocated)),
                    Decimal(str(item.used)),
                    Decimal(str(item.pending)),
                )
                if balance is None:
                    balance = LeaveBalance(
                        employee_id=employee.id,
                        leave_type_id=leave_type.id,
                        year=item.year,
                    )
                    session.add(balance)
                elif (balance.allocated, balance.used, balance.pending) == values:
                    unchanged = True
                if not unchanged:
                    balance.allocated, balance.used, balance.pending = values
                    await session.flush()
                local_id = balance.id
            if unchanged:
                result.add_duplicate(key, local_id, "Balance already matches the ERP value")
            else:
                result.add_accepted(key, local_id)
        except Exception as exc:
            log_erp_item_failure(key, exc, result.batch_id, result.endpoint)
            code, message, retryable = classify_erp_error(exc)
            result.add_failure(key, code=code, message=message, retryable=retryable)
    return result


@router.post(
    "/balances/bulk",
    response_model=ErpBatchResult,
    summary="Bulk sync ERP leave balances",
    description=(
        "Upserts ERP-authoritative balances per employee, leave type, and year. "
        "Each item is isolated: one bad row does not reject the page. Replaying "
        "an unchanged page reports `duplicate` and writes nothing."
    ),
)
async def sync_leave_balances_bulk(
    response: Response,
    balances: Annotated[list[ErpLeaveBalance], Body(max_length=5000)],
    batch_id: Annotated[str, Depends(resolve_batch_id)],
    principal: Annotated[ErpPrincipal, Depends(require_erp_scope("leaves:write"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ErpBatchResult:
    result = await sync_leave_balances(balances, session, batch_id=batch_id, client_id=principal.client_id)
    apply_batch_status(response, result)
    await record_batch(session, result, client_id=principal.client_id, http_status=response.status_code)
    await session.commit()
    return result


# ── Leave master data (ERP-owned) ──────────────────────────────────────────────


@router.post(
    "/periods",
    response_model=LeavePeriodRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_erp_scope("leave-master:write"))],
    summary="Create an ERP-owned leave period",
)
async def create_leave_period(
    data: LeavePeriodCreate, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> LeavePeriodRead:
    return await LeaveService(session).create_period(data)


@router.post(
    "/types",
    response_model=LeaveTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_erp_scope("leave-master:write"))],
    summary="Create an ERP-owned leave type",
)
async def create_leave_type(data: LeaveTypeCreate, session: Annotated[AsyncSession, Depends(get_async_session)]) -> LeaveTypeRead:
    return await LeaveService(session).create_type(data)


@router.patch(
    "/types/{type_id}",
    response_model=LeaveTypeRead,
    dependencies=[Depends(require_erp_scope("leave-master:write"))],
    summary="Update an ERP-owned leave type",
)
async def update_leave_type(
    type_id: int, data: LeaveTypeUpdate, session: Annotated[AsyncSession, Depends(get_async_session)]
) -> LeaveTypeRead:
    return await LeaveService(session).update_type(type_id, data)
