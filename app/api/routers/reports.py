from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission
from core.database import get_async_session
from db.models import User
from schemas.reports import (
    MonthlyAttendanceMatrixReport,
    MonthlyLeaveSummaryReport,
)
from services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/attendance-matrix", response_model=MonthlyAttendanceMatrixReport)
async def get_monthly_attendance_matrix(
    year: int = Query(...),
    month: int = Query(...),
    unit_id: int | None = Query(None),
    department_id: int | None = Query(None),
    _: User = Depends(require_permission("reports.attendance")),
    session: AsyncSession = Depends(get_async_session),
) -> MonthlyAttendanceMatrixReport:
    """Returns day-by-day attendance sheet matrix with monthly summary aggregates."""
    service = ReportService(session)
    return await service.get_monthly_attendance_matrix(
        year=year,
        month=month,
        unit_id=unit_id,
        department_id=department_id,
    )


@router.get("/leave-summary", response_model=MonthlyLeaveSummaryReport)
async def get_leave_summary_report(
    year: int = Query(...),
    unit_id: int | None = Query(None),
    department_id: int | None = Query(None),
    _: User = Depends(require_permission("reports.leave")),
    session: AsyncSession = Depends(get_async_session),
) -> MonthlyLeaveSummaryReport:
    """Returns annual leave balances (allocated, used, pending, available) across employees."""
    service = ReportService(session)
    return await service.get_leave_balance_summary(
        year=year,
        unit_id=unit_id,
        department_id=department_id,
    )
