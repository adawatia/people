import asyncio
import logging
from datetime import timedelta
from sqlalchemy import delete, text
from core.database import async_session_maker
from db.models import Notification, now_ist

logger = logging.getLogger("hrms")

async def run_notification_cleanup():
    """
    Cleans up old notifications based on the following rules:
    1. Delete unconditionally if older than 7 days.
    2. Delete if read (is_read=True) and older than 3 days.
    3. Keep at most the 50 most recent notifications per user (deletes the rest).
    """
    try:
        async with async_session_maker() as session:
            now = now_ist()
            
            # Rule 1: Delete all notifications older than 7 days
            seven_days_ago = now - timedelta(days=7)
            stmt1 = delete(Notification).where(Notification.created_at < seven_days_ago)
            res1 = await session.execute(stmt1)
            
            # Rule 2: Delete read notifications older than 3 days
            three_days_ago = now - timedelta(days=3)
            stmt2 = delete(Notification).where(
                Notification.is_read == True,
                Notification.created_at < three_days_ago
            )
            res2 = await session.execute(stmt2)

            # Rule 3: Keep max 50 recent notifications per user or role
            stmt3 = text("""
                WITH Ranked AS (
                    SELECT notification_id, ROW_NUMBER() OVER(
                        PARTITION BY COALESCE(CAST(user_id AS TEXT), target_role, 'global')
                        ORDER BY created_at DESC
                    ) as rn
                    FROM notifications
                )
                DELETE FROM notifications
                WHERE notification_id IN (
                    SELECT notification_id FROM Ranked WHERE rn > 50
                )
            """)

            res3 = await session.execute(stmt3)

            await session.commit()
            
            deleted_count = res1.rowcount + res2.rowcount + res3.rowcount
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old notifications.")
            
    except Exception as e:
        logger.error(f"Error during notification cleanup: {e}", exc_info=True)

async def notification_cleanup_loop():
    """
    Background loop that runs the cleanup task periodically.
    """
    # Sleep for an initial delay to not overload start-up
    await asyncio.sleep(60) 
    
    while True:
        await run_notification_cleanup()
        # Sleep for 6 hours before running again
        await asyncio.sleep(60 * 60 * 6)
