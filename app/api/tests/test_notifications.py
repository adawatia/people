import pytest
from core.database import async_session_maker
from db.models import Notification
from routers.notifications import create_notification


@pytest.mark.asyncio
async def test_notification_lifecycle():
    async with async_session_maker() as session:
        # 1. Create test notification
        notif = await create_notification(
            session,
            title="Test Leave Approved",
            message="Your leave request was approved.",
            notification_type="system",
            target_role="STAFF",
            reference_id=9999,
            reference_type="leave",
            link="/leave/9999",
        )
        await session.commit()
        assert notif.notification_id is not None
        assert notif.is_read is False

        # 2. Retrieve notification
        fetched = await session.get(Notification, notif.notification_id)
        assert fetched is not None
        assert fetched.title == "Test Leave Approved"

        # 3. Mark as read
        fetched.is_read = True
        await session.commit()

        # 4. Clean up test record
        await session.delete(fetched)
        await session.commit()
