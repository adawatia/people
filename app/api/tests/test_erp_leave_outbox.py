"""Regression coverage for the durable leave change feed and acknowledgements.

Requires the PostgreSQL test database (``DATABASE_URL`` ending in ``_test``) and
the ``3d4e5f607182`` migration (``erp_outbox_events``).

Each test works from a *baseline cursor* taken after its fixtures exist, so the
suite does not depend on the outbox being empty — earlier tests and the
migration backfill may leave unrelated pending events behind.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from core.database import async_session_maker
from core.erp_auth import ErpPrincipal
from db.models import Employee, ErpOutboxEvent, LeaveApplication, LeaveType, now_ist
from routers.erp_leaves import ErpLeaveAckRequest, acknowledge_leave_changes, get_leave_changes
from services.erp_outbox import enqueue_leave_event

PRINCIPAL = ErpPrincipal(client_id="outbox-test-client", scopes=frozenset({"*"}))


async def _seed_leave(session, *, status="PENDING", suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    employee = Employee(employee_code=f"OB{suffix}", first_name="Outbox")
    leave_type = LeaveType(name=f"Outbox Leave {suffix}", code=f"OB{suffix}")
    session.add_all([employee, leave_type])
    await session.flush()
    application = LeaveApplication(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 2),
        days_count=2,
        status=status,
        reason="Outbox test",
    )
    session.add(application)
    await session.flush()
    return employee, leave_type, application


async def _baseline(session) -> int:
    return int(await session.scalar(select(func.max(ErpOutboxEvent.sequence))) or 0)


async def _poll(session, cursor=None, limit=100, since=None):
    return await get_leave_changes(cursor=cursor, since=since, limit=limit, session=session)


async def _ack(session, ids, batch_id="ack-test-0001"):
    return await acknowledge_leave_changes(
        payload=ids, batch_id=batch_id, principal=PRINCIPAL, session=session
    )


async def _stage_event(session, application, event_type, *, created_at=None):
    await enqueue_leave_event(session, application, event_type)
    if created_at is not None:
        await session.flush()
        await session.execute(
            ErpOutboxEvent.__table__.update()
            .where(ErpOutboxEvent.event_id == application.erp_event_id)
            .values(created_at=created_at)
        )
    await session.commit()
    return application.erp_event_id


@pytest.mark.asyncio
async def test_feed_redelivers_until_acknowledged_and_tracks_attempts():
    async with async_session_maker() as session:
        employee, leave_type, application = await _seed_leave(session, status="APPROVED")
        cursor = await _baseline(session)
        await session.commit()
        event_id = await _stage_event(session, application, "APPROVED")

        first = await _poll(session, cursor=str(cursor))
        mine = [item for item in first.items if item.event_id == event_id]
        assert len(mine) == 1
        assert mine[0].employee_code == employee.employee_code
        assert mine[0].leave_code == leave_type.code
        assert first.next_cursor == str(first.items[-1].sequence)

        # Not acknowledged: the very next poll with the same cursor redelivers it.
        second = await _poll(session, cursor=str(cursor))
        assert event_id in [item.event_id for item in second.items]
        attempts = await session.scalar(
            select(ErpOutboxEvent.delivery_attempts).where(ErpOutboxEvent.event_id == event_id)
        )
        assert attempts == 2
        assert (
            await session.scalar(
                select(ErpOutboxEvent.last_delivered_at).where(ErpOutboxEvent.event_id == event_id)
            )
            is not None
        )


@pytest.mark.asyncio
async def test_acknowledgement_is_idempotent_and_removes_the_event_from_the_feed():
    async with async_session_maker() as session:
        _, _, application = await _seed_leave(session, status="REJECTED")
        cursor = await _baseline(session)
        await session.commit()
        event_id = await _stage_event(session, application, "REJECTED")

        first = await _ack(session, [event_id])
        assert first.acknowledged == [event_id]
        assert first.already_acknowledged == []

        # Replaying the acknowledgement is a no-op, not an error.
        second = await _ack(session, [event_id])
        assert second.acknowledged == []
        assert second.already_acknowledged == [event_id]
        assert second.unknown == []

        feed = await _poll(session, cursor=str(cursor))
        assert event_id not in [item.event_id for item in feed.items]

        row = await session.scalar(
            select(ErpOutboxEvent).where(ErpOutboxEvent.event_id == event_id)
        )
        assert row.acknowledged_at is not None
        assert row.acknowledged_by == PRINCIPAL.client_id


@pytest.mark.asyncio
async def test_equal_timestamps_are_paged_without_skipping_or_repeating():
    stamp = now_ist().replace(microsecond=123456)
    async with async_session_maker() as session:
        application_ids = []
        for _ in range(3):
            _, _, application = await _seed_leave(session, status="APPROVED")
            application_ids.append(application)
        cursor = await _baseline(session)
        await session.commit()

        # Same creation timestamp for all three: a timestamp cursor would skip
        # two of them once the client advanced past `stamp`.
        ids = [
            await _stage_event(session, application, "APPROVED", created_at=stamp)
            for application in application_ids
        ]

        seen = []
        page_cursor = str(cursor)
        for _ in range(10):
            page = await _poll(session, cursor=page_cursor, limit=1)
            seen.extend(item.event_id for item in page.items if item.event_id in ids)
            if not page.has_more:
                break
            page_cursor = page.next_cursor
        assert sorted(seen) == sorted(ids)
        assert len(seen) == len(set(seen))


@pytest.mark.asyncio
async def test_partial_acknowledgement_keeps_the_rest_pending():
    async with async_session_maker() as session:
        _, _, first_app = await _seed_leave(session, status="APPROVED")
        _, _, second_app = await _seed_leave(session, status="APPROVED")
        cursor = await _baseline(session)
        await session.commit()
        first_event = await _stage_event(session, first_app, "APPROVED")
        second_event = await _stage_event(session, second_app, "APPROVED")

        ack = await _ack(session, [first_event])
        assert ack.acknowledged == [first_event]

        feed = await _poll(session, cursor=str(cursor))
        remaining = [item.event_id for item in feed.items]
        assert second_event in remaining
        assert first_event not in remaining
        assert ack.pending_remaining >= 1


@pytest.mark.asyncio
async def test_duplicate_acknowledgement_ids_are_collapsed():
    async with async_session_maker() as session:
        _, _, application = await _seed_leave(session, status="APPROVED")
        await session.commit()
        event_id = await _stage_event(session, application, "APPROVED")

        ack = await _ack(session, [event_id, event_id, event_id])
        assert ack.acknowledged == [event_id]
        assert ack.unknown == []


@pytest.mark.asyncio
async def test_unknown_and_foreign_entity_ids_are_reported_not_acknowledged():
    async with async_session_maker() as session:
        other = ErpOutboxEvent(
            event_id=f"OTHER-{uuid.uuid4().hex}",
            entity_type="OTHER_ENTITY",
            entity_id=1,
            event_type="CREATED",
            payload={"x": 1},
        )
        session.add(other)
        await session.commit()

        ack = await _ack(session, ["LEAVE-999999-APPROVED", other.event_id])
        assert ack.acknowledged == []
        assert sorted(ack.unknown) == sorted(["LEAVE-999999-APPROVED", other.event_id])

        row = await session.scalar(select(ErpOutboxEvent).where(ErpOutboxEvent.event_id == other.event_id))
        assert row.acknowledged_at is None


@pytest.mark.asyncio
async def test_old_cursor_after_acknowledgement_yields_no_new_events():
    async with async_session_maker() as session:
        _, _, application = await _seed_leave(session, status="APPROVED")
        cursor = await _baseline(session)
        await session.commit()
        event_id = await _stage_event(session, application, "APPROVED")

        page = await _poll(session, cursor=str(cursor))
        assert event_id in [item.event_id for item in page.items]
        await _ack(session, [event_id])

        # A client that restarts with the cursor it already used must not see the
        # acknowledged event again, and nothing else of ours is pending.
        replay = await _poll(session, cursor=str(cursor))
        assert event_id not in [item.event_id for item in replay.items]
        # Whatever remains pending is still addressable from an old cursor.
        if replay.items:
            assert replay.next_cursor is not None


@pytest.mark.asyncio
async def test_new_events_arrive_while_an_earlier_batch_is_being_processed():
    async with async_session_maker() as session:
        _, _, application = await _seed_leave(session, status="APPROVED")
        cursor = await _baseline(session)
        await session.commit()
        first_event = await _stage_event(session, application, "APPROVED")

        page = await _poll(session, cursor=str(cursor))
        assert first_event in [item.event_id for item in page.items]

        # ERP is still processing the first page when a new decision lands.
        application.status = "CANCELLED"
        await session.flush()
        second_event = await _stage_event(session, application, "CANCELLED")

        await _ack(session, [first_event])
        following = await _poll(session, cursor=page.next_cursor)
        assert second_event in [item.event_id for item in following.items]


@pytest.mark.asyncio
async def test_legacy_since_cursor_redelivers_equal_timestamps():
    stamp = now_ist().replace(microsecond=654321)
    async with async_session_maker() as session:
        ids = []
        for _ in range(2):
            _, _, application = await _seed_leave(session, status="APPROVED")
            ids.append(await _stage_event(session, application, "APPROVED", created_at=stamp))

        page = await _poll(session, since=stamp)
        delivered = [item.event_id for item in page.items]
        # `since` is treated as strictly-before, so rows created exactly at
        # `stamp` are redelivered rather than skipped.
        assert all(event_id in delivered for event_id in ids)


@pytest.mark.asyncio
async def test_acknowledging_an_older_event_does_not_mask_a_newer_one():
    async with async_session_maker() as session:
        _, _, application = await _seed_leave(session, status="APPROVED")
        await session.commit()

        approved_event = await _stage_event(session, application, "APPROVED")
        await _ack(session, [approved_event])
        row = await session.get(LeaveApplication, application.id)
        await session.refresh(row)
        assert row.erp_sync_status == "ACKNOWLEDGED"

        application.status = "CANCELLED"
        application.actioned_at = now_ist()
        await session.flush()
        await session.commit()
        cancelled_event = await _stage_event(session, application, "CANCELLED")

        await session.refresh(row)
        assert row.erp_sync_status == "PENDING"

        feed = await _poll(session, cursor=str(0), limit=500)
        assert cancelled_event in [item.event_id for item in feed.items]


@pytest.mark.asyncio
async def test_outbox_row_is_lost_when_the_decision_transaction_rolls_back():
    async with async_session_maker() as session:
        _, _, application = await _seed_leave(session, status="APPROVED")
        await session.commit()
        event_id = await enqueue_leave_event(session, application, "APPROVED")
        await session.flush()
        assert await session.scalar(select(ErpOutboxEvent.sequence).where(ErpOutboxEvent.event_id == event_id))

        await session.rollback()
        assert (
            await session.scalar(select(ErpOutboxEvent.sequence).where(ErpOutboxEvent.event_id == event_id))
            is None
        )


@pytest.mark.asyncio
async def test_repeating_the_same_transition_does_not_duplicate_the_event():
    async with async_session_maker() as session:
        _, _, application = await _seed_leave(session, status="APPROVED")
        await session.commit()

        first = await enqueue_leave_event(session, application, "APPROVED")
        second = await enqueue_leave_event(session, application, "APPROVED")
        await session.commit()
        assert first == second == f"LEAVE-{application.id}-APPROVED"
        count = await session.scalar(
            select(func.count()).select_from(ErpOutboxEvent).where(ErpOutboxEvent.event_id == first)
        )
        assert count == 1


def test_ack_request_model_rejects_oversized_batches():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ErpLeaveAckRequest(event_ids=[f"LEAVE-{index}-APPROVED" for index in range(501)])


@pytest.mark.asyncio
async def test_feed_ignores_acknowledged_rows_and_orders_by_sequence():
    async with async_session_maker() as session:
        _, _, application = await _seed_leave(session, status="APPROVED")
        cursor = await _baseline(session)
        await session.commit()
        approved = await _stage_event(session, application, "APPROVED")
        application.status = "CANCELLED"
        application.actioned_at = now_ist() + timedelta(seconds=1)
        await session.flush()
        cancelled = await _stage_event(session, application, "CANCELLED")
        await _ack(session, [approved])

        page = await _poll(session, cursor=str(cursor), limit=500)
        ours = [item for item in page.items if item.event_id in {approved, cancelled}]
        assert [item.event_id for item in ours] == [cancelled]
