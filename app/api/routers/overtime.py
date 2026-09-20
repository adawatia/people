from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from db.models import User
from schemas.overtime import (
    OvertimeRecordRead,
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
