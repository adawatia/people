import math
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list, description="List of items for current page")
    total: int = Field(..., description="Total count of items matching filters")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether a next page is available")
    has_prev: bool = Field(..., description="Whether a previous page is available")


class PaginationParams:
    def __init__(self, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
        self.page = page
        self.page_size = page_size


def page_metadata(total: int, page: int, page_size: int) -> dict:
    total_pages = max(1, math.ceil(total / page_size))
    return {"total": total, "page": page, "page_size": page_size, "total_pages": total_pages,
                "has_next": page < total_pages, "has_prev": page > 1}


def ordered(query, fields: dict, sort_by: str | None, sort_order: str, default: str, identifier):
    from fastapi import HTTPException
    if (sort_by or default) not in fields or sort_order not in ("asc", "desc"):
        raise HTTPException(422, "Unsupported sort field or order")
    column = fields[sort_by or default]
    direction = lambda value: value.desc() if sort_order == "desc" else value.asc()
    return query.order_by(None).order_by(direction(column), direction(identifier))


def employee_search(query, employee, search: str | None):
    from sqlalchemy import func, or_
    if not search or not search.strip():
        return query
    name = employee.first_name + " " + func.coalesce(employee.last_name, "")
    return query.where(or_(name.icontains(search.strip(), autoescape=True),
                           employee.employee_code.icontains(search.strip(), autoescape=True)))


async def paginate(session: AsyncSession, query: Select, page: int = 1,
                   page_size: int = 25, count_query=None) -> dict:
    from fastapi import HTTPException
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(422, "Invalid pagination: page >= 1 and page_size between 1 and 100")
    if count_query is None:
        count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = await session.scalar(count_query) or 0
    result = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
    return dict(items=list(result.scalars().all()), **page_metadata(total, page, page_size))
