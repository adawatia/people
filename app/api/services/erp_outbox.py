"""Transactional outbox for changes HRMS owns and ERP must consume.

A leave decision is only useful to the ERP if the notification cannot be lost:
writing the event in a *separate* step (or as a mutable column on the leave row)
means a crash between the two, or a second transition before the first is
acknowledged, silently drops an outcome the ERP never saw.

So every transition stages one immutable row here, in the same transaction as
the business change, and the feed/ack protocol in ``routers/erp_leaves.py``
reads and acknowledges those rows. Acknowledged rows are retained (see
``ERP_INTEGRATION_OUTBOX_RETENTION_DAYS``) so support can reconstruct what ERP
was told and when.

Event ids stay deterministic — ``LEAVE-{id}-{EVENT}`` — which is the key the ERP
already deduplicates on. A retried transition therefore enqueues nothing new,
while a later transition on the same application (approve → cancel) remains an
independent event with its own acknowledgement.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Employee, ErpOutboxEvent, LeaveApplication, LeaveType

LEAVE_ENTITY = "LEAVE_APPLICATION"


async def enqueue_leave_event(
    session: AsyncSession,
    application: LeaveApplication,
    event_type: str,
) -> str:
    """Stage the outbound event in the caller's transaction and return its id.

    Callers must be inside the transaction that performs the state change and
    must commit once; the event then becomes visible to the ERP atomically with
    the decision, or not at all.
    """
    employee_code = await session.scalar(
        select(Employee.employee_code).where(Employee.id == application.employee_id)
    )
    leave_code = await session.scalar(
        select(LeaveType.code).where(LeaveType.id == application.leave_type_id)
    )
    event_id = f"LEAVE-{application.id}-{event_type}"
    payload = {
        "leave_id": application.id,
        "employee_code": employee_code,
        "leave_code": leave_code,
        "from_date": application.from_date.isoformat(),
        "to_date": application.to_date.isoformat(),
        "days": float(application.days_count),
        "status": application.status,
        "reason": application.reason,
        "rejection_reason": application.rejection_reason,
        "approved_at": application.actioned_at.isoformat() if application.actioned_at else None,
        "event_type": event_type,
    }
    await session.execute(
        pg_insert(ErpOutboxEvent)
        .values(
            event_id=event_id,
            entity_type=LEAVE_ENTITY,
            entity_id=application.id,
            event_type=event_type,
            payload=payload,
        )
        # A retried or duplicated transition must not create a second event.
        .on_conflict_do_nothing(index_elements=["event_id"])
    )

    # Denormalised mirror kept for the existing read models; the outbox row is
    # the source of truth for delivery.
    application.erp_event_id = event_id
    application.erp_sync_status = "PENDING"
    application.erp_synced_at = None
    return event_id


async def pending_event_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(ErpOutboxEvent)
            .where(ErpOutboxEvent.entity_type == LEAVE_ENTITY, ErpOutboxEvent.acknowledged_at.is_(None))
        )
        or 0
    )
