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
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(10, ge=1, le=500, description="Items per page (e.g. 10, 15, 20, 25, 50, 100, 500)"),
        all: bool = Query(False, description="Fetch all records without pagination limits"),
    ):
        self.page = page
        self.page_size = page_size
        self.all = all


async def paginate(
    session: AsyncSession,
    query: Select,
    page: int = 1,
    page_size: int = 10,
    all_records: bool = False,
) -> dict:
    """
    Executes an async paginated query and returns dictionary matching PaginatedResponse structure.
    """
    # 1. Calculate total matching items
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_result = await session.scalar(count_query)
    total = total_result if total_result is not None else 0

    # 2. Return all records if requested
    if all_records:
        result = await session.execute(query)
        items = result.scalars().all()
        return {
            "items": items,
            "total": total,
            "page": 1,
            "page_size": total if total > 0 else 10,
            "total_pages": 1,
            "has_next": False,
            "has_prev": False,
        }

    # 3. Calculate pagination math
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    has_next = page < total_pages
    has_prev = page > 1

    # 4. Fetch the slice
    offset = (page - 1) * page_size
    paged_query = query.offset(offset).limit(page_size)
    result = await session.execute(paged_query)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_prev": has_prev,
    }
