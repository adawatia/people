from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from db.models import Notification, User
from schemas.notifications import (
    NotificationMarkRead,
    NotificationRead,
    NotificationUnreadCount,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


async def build_notification_filter(user: User, session: AsyncSession):
    """Personal notifications plus role-wide HRMS broadcasts."""
    if user.is_superuser:
        return None  # All notifications

    return or_(
        Notification.user_id == user.id,
        Notification.target_role.in_(["ALL", "STAFF", "HR", "MANAGER", "EMPLOYEE"]),
        Notification.notification_type.in_(["system"]),
    )


async def create_notification(
    session: AsyncSession,
    *,
    title: str,
    message: str,
    notification_type: str,
    user_id: int | None = None,
    target_role: str | None = None,
    reference_id: int | None = None,
    reference_type: str | None = None,
    link: str | None = None,
) -> Notification:
    notif = Notification(
        title=title,
        message=message,
        notification_type=notification_type,
        user_id=user_id,
        target_role=target_role,
        reference_id=reference_id,
        reference_type=reference_type,
        link=link,
        is_read=False,
    )
    session.add(notif)
    return notif


@router.get("", response_model=list[NotificationRead], summary="Fetch recent notifications for logged in user")
async def get_notifications(
    limit: int = 30,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
):
    filt = await build_notification_filter(current_user, session)
    query = select(Notification)
    if filt is not None:
        query = query.where(filt)
    query = query.order_by(Notification.created_at.desc()).limit(min(limit, 100))

    result = await session.scalars(query)
    return list(result.all())


@router.get("/unread-count", response_model=NotificationUnreadCount, summary="Get unread notifications count")
async def get_unread_count(
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
):
    filt = await build_notification_filter(current_user, session)
    query = select(func.count(Notification.notification_id)).where(Notification.is_read.is_(False))
    if filt is not None:
        query = query.where(filt)

    count = await session.scalar(query) or 0
    return NotificationUnreadCount(unread_count=count)


@router.patch("/{id}/read", response_model=NotificationRead, summary="Mark single notification as read")
async def mark_notification_read(
    id: int,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
):
    notif = await session.get(Notification, id)
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    if not current_user.is_superuser and notif.user_id is not None and notif.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to mark this notification as read.",
        )

    notif.is_read = True
    await session.commit()
    await session.refresh(notif)
    return notif


@router.post("/mark-all-read", summary="Mark all visible notifications as read")
async def mark_all_read(
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
):
    filt = await build_notification_filter(current_user, session)
    query = update(Notification).where(Notification.is_read.is_(False))
    if filt is not None:
        query = query.where(filt)
    query = query.values(is_read=True)

    await session.execute(query)
    await session.commit()
    return {"message": "All notifications marked as read"}
