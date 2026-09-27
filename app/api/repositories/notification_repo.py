from sqlalchemy import exists, func, literal, select
from sqlalchemy.dialects.postgresql import insert

from core.pagination import ordered, paginate
from db.models import Notification, NotificationReceipt, now_ist


class NotificationRepository:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _receipt_exists(user_id: int):
        return exists().where(
            NotificationReceipt.notification_id == Notification.notification_id,
            NotificationReceipt.user_id == user_id,
        )

    async def list_page(
        self, audience, user_id, page, page_size, unread=None, search=None, sort_by=None, sort_order="desc"
    ):
        query = select(Notification)
        if audience is not None:
            query = query.where(audience)
        if unread is not None:
            receipt = self._receipt_exists(user_id)
            query = query.where(~receipt if unread else receipt)
        if search:
            query = query.where(Notification.title.icontains(search.strip(), autoescape=True))
        query = ordered(
            query,
            {"created_at": Notification.created_at, "id": Notification.notification_id},
            sort_by,
            sort_order,
            "created_at",
            Notification.notification_id,
        )
        return await paginate(self.session, query, page, page_size)

    async def read_notification_ids(self, user_id: int, notification_ids: list[int]) -> set[int]:
        if not notification_ids:
            return set()
        statement = select(NotificationReceipt.notification_id).where(
            NotificationReceipt.user_id == user_id,
            NotificationReceipt.notification_id.in_(notification_ids),
        )
        return set(await self.session.scalars(statement))

    async def unread_count(self, audience, user_id: int) -> int:
        statement = select(Notification.notification_id).where(~self._receipt_exists(user_id))
        if audience is not None:
            statement = statement.where(audience)
        count_statement = select(func.count()).select_from(statement.subquery())
        return int(await self.session.scalar(count_statement) or 0)

    async def mark_read(self, notification_id: int, user_id: int) -> None:
        statement = (
            insert(NotificationReceipt)
            .values(
                notification_id=notification_id,
                user_id=user_id,
                read_at=now_ist(),
            )
            .on_conflict_do_nothing(constraint="uq_notification_receipt_user")
        )
        await self.session.execute(statement)

    async def mark_visible_read(self, audience, user_id: int) -> None:
        visible = select(
            Notification.notification_id,
            literal(user_id),
            literal(now_ist()),
        )
        if audience is not None:
            visible = visible.where(audience)
        statement = (
            insert(NotificationReceipt)
            .from_select(["notification_id", "user_id", "read_at"], visible)
            .on_conflict_do_nothing(constraint="uq_notification_receipt_user")
        )
        await self.session.execute(statement)
