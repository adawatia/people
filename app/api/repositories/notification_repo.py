from sqlalchemy import select

from core.pagination import ordered, paginate
from db.models import Notification


class NotificationRepository:
    def __init__(self, session):
        self.session = session

    async def list_page(self, audience, page, page_size, unread=None, search=None, sort_by=None, sort_order="desc"):
        query = select(Notification)
        if audience is not None:
            query = query.where(audience)
        if unread is not None:
            query = query.where(Notification.is_read.is_(not unread))
        if search:
            query = query.where(Notification.title.icontains(search.strip(), autoescape=True))
        query = ordered(query, {"created_at": Notification.created_at, "id": Notification.notification_id},
                        sort_by, sort_order, "created_at", Notification.notification_id)
        return await paginate(self.session, query, page, page_size)
