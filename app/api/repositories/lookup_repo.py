from sqlalchemy import select
from sqlalchemy.orm import noload, selectinload

from core.pagination import ordered, paginate
from db.models import HolidayList, Unit


class LookupRepository:
    def __init__(self, session):
        self.session = session

    async def list_page(self, model, page=1, page_size=25, search=None, sort_by=None,
                        sort_order="asc", filters=None):
        query = select(model)
        if model is Unit:
            query = query.options(noload(Unit.departments))
        if model is HolidayList:
            query = query.options(selectinload(HolidayList.holidays))
        for name, value in (filters or {}).items():
            if value is not None:
                query = query.where(getattr(model, name) == value)
        name_column = getattr(model, "name", None)
        if search and name_column is not None:
            query = query.where(name_column.icontains(search.strip(), autoescape=True))
        query = ordered(query, ({"name": name_column, "id": model.id} if name_column is not None else {"id": model.id}), sort_by, sort_order,
                        "name" if name_column is not None else "id", model.id)
        return await paginate(self.session, query, page, page_size)
