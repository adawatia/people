from datetime import date
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas.work_arrangements import (
    WorkArrangementAction,
    WorkArrangementCreate,
    WorkArrangementRead,
)
from services.work_arrangement_service import WorkArrangementService

router = APIRouter(prefix="/work-arrangements", tags=["work-arrangements"])


@router.get("/", response_model=list[WorkArrangementRead])
async def list_work_arrangements(
    employee_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    arrangement_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[WorkArrangementRead]:
    service = WorkArrangementService(session)
    return await service.list_requests(
        employee_id=employee_id,
        status=status_filter,
        arrangement_type=arrangement_type,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/{req_id}", response_model=WorkArrangementRead)
async def get_work_arrangement(
    req_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    return await service.get_request(req_id)


@router.post("/", response_model=WorkArrangementRead, status_code=status.HTTP_201_CREATED)
async def create_work_arrangement(
    data: WorkArrangementCreate,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    return await service.create_request(data)


@router.patch("/{req_id}/approve", response_model=WorkArrangementRead)
async def approve_work_arrangement(
    req_id: int,
    current_user: User = Depends(require_permission("leave.approve")),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    return await service.approve_request(req_id, current_user.id)


@router.patch("/{req_id}/reject", response_model=WorkArrangementRead)
async def reject_work_arrangement(
    req_id: int,
    action: WorkArrangementAction,
    current_user: User = Depends(require_permission("leave.reject")),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    return await service.reject_request(req_id, current_user.id, action.rejection_reason)


@router.patch("/{req_id}/cancel", response_model=WorkArrangementRead)
async def cancel_work_arrangement(
    req_id: int,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    return await service.cancel_request(req_id, current_user.id)
