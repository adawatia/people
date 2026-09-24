from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.business_roles import (
    DEPARTMENT_MANAGER,
    HR_ADMIN,
    ORGANIZATION_OWNER,
    resolve_business_role,
)
from core.database import get_async_session
from core.pagination import PaginatedResponse
from db.models import Employee, Notification, User
from repositories.notification_repo import NotificationRepository
from schemas.notifications import (
    NotificationRead,
    NotificationUnreadCount,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


async def build_notification_filter(user: User, session: AsyncSession):
    """Personal notifications plus role-wide HRMS broadcasts."""
    if user.is_superuser:
        return None  # All notifications

    employee = await session.scalar(select(Employee).where(Employee.user_id == user.id))
    target_roles = notification_target_roles(
        resolve_business_role(employee) if employee else None,
        employee_linked=employee is not None,
    )
    return or_(
        Notification.user_id == user.id,
        and_(
            Notification.user_id.is_(None),
            func.upper(func.trim(Notification.target_role)).in_(target_roles),
        ),
        and_(
            Notification.user_id.is_(None),
            Notification.target_role.is_(None),
            Notification.notification_type == "system",
        ),
    )


def notification_target_roles(business_role: str | None, *, employee_linked: bool = True) -> set[str]:
    """Return broad plus role-specific broadcast audiences for one employee."""
    roles = {"ALL", "STAFF"}
    if not employee_linked:
        return roles
    if business_role == HR_ADMIN:
        roles.add("HR")
    elif business_role == DEPARTMENT_MANAGER:
        roles.add("MANAGER")
    elif business_role == ORGANIZATION_OWNER:
        roles.add("OWNER")
    else:
        roles.add("EMPLOYEE")
    return roles


def can_read_notification(user: User, notification: Notification, target_roles: set[str]) -> bool:
    if user.is_superuser or notification.user_id == user.id:
        return True
    if notification.user_id is not None:
        return False
    if notification.target_role is None:
        return notification.notification_type == "system"
    return notification.target_role.strip().upper() in target_roles


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
        target_role=(target_role.strip().upper() or None) if target_role else None,
        reference_id=reference_id,
        reference_type=reference_type,
        link=link,
        is_read=False,
    )
    session.add(notif)
    return notif


@router.get("", response_model=PaginatedResponse[NotificationRead], summary="Fetch recent notifications for logged in user")
async def get_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    unread: bool | None = None,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
):
    filt = await build_notification_filter(current_user, session)
    return await NotificationRepository(session).list_page(
        filt, page, page_size, unread, search, sort_by, sort_order)


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

    employee = None
    if not current_user.is_superuser and notif.user_id != current_user.id:
        employee = await session.scalar(select(Employee).where(Employee.user_id == current_user.id))
    roles = notification_target_roles(
        resolve_business_role(employee) if employee else None,
        employee_linked=employee is not None,
    )
    if not can_read_notification(current_user, notif, roles):
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
