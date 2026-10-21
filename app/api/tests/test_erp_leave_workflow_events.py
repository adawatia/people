"""Leave decisions must emit exactly one outbound event, in their transaction.

Requires the PostgreSQL test database.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.database import async_session_maker
from db.models import Employee, ErpOutboxEvent, LeaveApplication, LeaveType, User
from services.leave_service import LeaveService


async def _seed(session):
    suffix = uuid.uuid4().hex[:8]
    employee = Employee(employee_code=f"WF{suffix}", first_name="Workflow")
    leave_type = LeaveType(name=f"Workflow Leave {suffix}", code=f"WF{suffix}", is_paid=False)
    approver = User(
        email=f"wf_{suffix}@example.com",
        username=f"wf_{suffix}",
        hashed_password="not-a-login",
        is_active=True,
        is_verified=True,
    )
    session.add_all([employee, leave_type, approver])
    await session.flush()
    application = LeaveApplication(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        from_date=date(2026, 12, 14),
        to_date=date(2026, 12, 15),
        days_count=2,
        status="PENDING",
        reason="Workflow test",
    )
    session.add(application)
    await session.commit()
    return employee, leave_type, approver, application


async def _events(session, application_id):
    return list(
        (
            await session.execute(
                select(ErpOutboxEvent)
                .where(
                    ErpOutboxEvent.entity_type == "LEAVE_APPLICATION",
                    ErpOutboxEvent.entity_id == application_id,
                )
                .order_by(ErpOutboxEvent.sequence)
            )
        ).scalars()
    )


@pytest.mark.asyncio
async def test_approval_emits_one_event_and_marks_the_mirror_pending():
    async with async_session_maker() as session:
        _, _, approver, application = await _seed(session)
        await LeaveService(session).approve_leave(application.id, approver.id)

        events = await _events(session, application.id)
        assert [event.event_type for event in events] == ["APPROVED"]
        assert events[0].event_id == f"LEAVE-{application.id}-APPROVED"
        assert events[0].payload["leave_id"] == application.id

        row = await session.get(LeaveApplication, application.id)
        await session.refresh(row)
        assert row.status == "APPROVED"
        assert row.erp_sync_status == "PENDING"


@pytest.mark.asyncio
async def test_a_second_approval_is_rejected_without_a_second_event():
    async with async_session_maker() as session:
        _, _, approver, application = await _seed(session)
        service = LeaveService(session)
        await service.approve_leave(application.id, approver.id)

        with pytest.raises(HTTPException) as exc:
            await service.approve_leave(application.id, approver.id)
        assert exc.value.status_code == 400

        assert len(await _events(session, application.id)) == 1


@pytest.mark.asyncio
async def test_rejection_emits_a_rejected_event():
    async with async_session_maker() as session:
        _, _, approver, application = await _seed(session)
        await LeaveService(session).reject_leave(application.id, approver.id, rejection_reason="No cover")

        events = await _events(session, application.id)
        assert [event.event_type for event in events] == ["REJECTED"]
        assert events[0].payload["rejection_reason"] == "No cover"


@pytest.mark.asyncio
async def test_cancelling_an_approved_leave_appends_a_cancelled_event():
    async with async_session_maker() as session:
        _, _, approver, application = await _seed(session)
        service = LeaveService(session)
        await service.approve_leave(application.id, approver.id)
        await service.cancel_leave(application.id, approver.id)

        events = await _events(session, application.id)
        assert [event.event_type for event in events] == ["APPROVED", "CANCELLED"]
        assert events[0].sequence < events[1].sequence


@pytest.mark.asyncio
async def test_a_failed_approval_rolls_back_its_event_and_state():
    async with async_session_maker() as session:
        _, _, _, application = await _seed(session)
        application_id = application.id

        # actioned_by is a real foreign key: an unknown approver fails the write.
        with pytest.raises(IntegrityError):
            await LeaveService(session).approve_leave(application_id, 2_000_000_000)
        await session.rollback()

        assert await _events(session, application_id) == []
        row = await session.get(LeaveApplication, application_id)
        await session.refresh(row)
        assert row.status == "PENDING"
        assert row.erp_event_id is None


@pytest.mark.asyncio
async def test_event_payload_is_a_snapshot_independent_of_later_renames():
    async with async_session_maker() as session:
        _, leave_type, approver, application = await _seed(session)
        await LeaveService(session).approve_leave(application.id, approver.id)

        # Names are unique; use a run-specific one so repeated runs are safe.
        leave_type.name = f"Renamed after approval {uuid.uuid4().hex[:8]}"
        await session.commit()

        events = await _events(session, application.id)
        assert events[0].payload["leave_code"] == leave_type.code
        assert events[0].payload["days"] == 2.0


@pytest.mark.asyncio
async def test_event_count_matches_decision_count():
    async with async_session_maker() as session:
        _, _, approver, application = await _seed(session)
        await LeaveService(session).approve_leave(application.id, approver.id)
        total = await session.scalar(
            select(func.count())
            .select_from(ErpOutboxEvent)
            .where(ErpOutboxEvent.entity_id == application.id)
        )
        assert total == 1
