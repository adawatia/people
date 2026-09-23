from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission
from core.database import get_async_session
from core.employee_access import get_employee_scope
from db.models import User
from schemas.reports import (
    MonthlyAttendanceMatrixReport,
    MonthlyLeaveSummaryReport,
)
from services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


async def _scoped_report_filters(
    user: User,
    session: AsyncSession,
    unit_id: int | None,
    department_id: int | None,
) -> tuple[int | None, int | None]:
    """Force the report filters inside the caller's row scope.

    Organization-scoped callers (Organization Owner, organization HR, Super
    Admin) may choose their own filters; a unit- or department-scoped caller is
    pinned to that unit/department regardless of the query string.
    """
    if user.is_superuser:
        return unit_id, department_id
    scope = await get_employee_scope(user, session)
    if scope.organization:
        return unit_id, department_id
    if scope.unit_ids:
        return next(iter(scope.unit_ids)), None
    if scope.department_ids:
        return None, next(iter(scope.department_ids))
    raise HTTPException(status_code=403, detail="Your business role has no report scope assigned")


@router.get("/attendance-matrix", response_model=MonthlyAttendanceMatrixReport)
async def get_monthly_attendance_matrix(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    unit_id: int | None = Query(None),
    department_id: int | None = Query(None),
    _: User = Depends(require_permission("reports.attendance")),
    session: AsyncSession = Depends(get_async_session),
) -> MonthlyAttendanceMatrixReport:
    """Returns day-by-day attendance sheet matrix with monthly summary aggregates."""
    unit_id, department_id = await _scoped_report_filters(_, session, unit_id, department_id)
    service = ReportService(session)
    return await service.get_monthly_attendance_matrix(
        year=year,
        month=month,
        unit_id=unit_id,
        department_id=department_id,
    )


@router.get("/leave-summary", response_model=MonthlyLeaveSummaryReport)
async def get_leave_summary_report(
    year: int = Query(..., ge=2000, le=2100),
    unit_id: int | None = Query(None),
    department_id: int | None = Query(None),
    _: User = Depends(require_permission("reports.leave")),
    session: AsyncSession = Depends(get_async_session),
) -> MonthlyLeaveSummaryReport:
    """Returns annual leave balances (allocated, used, pending, available) across employees."""
    unit_id, department_id = await _scoped_report_filters(_, session, unit_id, department_id)
    service = ReportService(session)
    return await service.get_leave_balance_summary(
        year=year,
        unit_id=unit_id,
        department_id=department_id,
    )
