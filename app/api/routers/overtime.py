from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas.overtime import (
    OvertimeApprovalCreate,
    OvertimeRecordRead,
    OvertimeRejectionCreate,
    OvertimeSummary,
)
from services.overtime_service import OvertimeService

router = APIRouter(prefix="/overtime", tags=["overtime"])


@router.get("/", response_model=list[OvertimeRecordRead])
async def list_overtime(
    employee_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[OvertimeRecordRead]:
    service = OvertimeService(session)
    return await service.list_overtime(employee_id=employee_id, status=status_filter)


@router.get("/{ot_id}", response_model=OvertimeRecordRead)
async def get_overtime(
    ot_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeRecordRead:
    service = OvertimeService(session)
    return await service.get_overtime(ot_id)


@router.patch("/{ot_id}/approve", response_model=OvertimeRecordRead)
async def approve_overtime(
    ot_id: int,
    data: OvertimeApprovalCreate,
    current_user: User = Depends(require_permission("overtime.approve")),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeRecordRead:
    service = OvertimeService(session)
    return await service.approve_overtime(
        ot_id=ot_id,
        data=data,
        actioned_by_user_id=current_user.id,
    )


@router.patch("/{ot_id}/reject", response_model=OvertimeRecordRead)
async def reject_overtime(
    ot_id: int,
    data: OvertimeRejectionCreate,
    current_user: User = Depends(require_permission("overtime.approve")),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeRecordRead:
    service = OvertimeService(session)
    return await service.reject_overtime(
        ot_id=ot_id,
        data=data,
        actioned_by_user_id=current_user.id,
    )


@router.get("/employee/{emp_id}/summary", response_model=OvertimeSummary)
async def get_overtime_summary(
    emp_id: int,
    month: int = Query(...),
    year: int = Query(...),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeSummary:
    service = OvertimeService(session)
    return await service.get_overtime_summary(employee_id=emp_id, month=month, year=year)

