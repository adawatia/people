from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission
from core.database import get_async_session
from core.employee_access import get_current_employee
from db.models import User
from schemas.reports import (
    MonthlyAttendanceMatrixReport,
    MonthlyLeaveSummaryReport,
)
from services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


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
    if not _.is_superuser:
        employee = await get_current_employee(_, session)
        if employee.role == "ORGANIZATION_OWNER":
            pass
        elif employee.role == "HR_ADMIN":
            if employee.unit_id is None:
                raise HTTPException(status_code=403, detail="HR administrator is not assigned to a unit")
            unit_id, department_id = employee.unit_id, None
        elif employee.role == "DEPARTMENT_MANAGER":
            if employee.department_id is None:
                raise HTTPException(status_code=403, detail="Department manager is not assigned to a department")
            unit_id, department_id = None, employee.department_id
        else:
            raise HTTPException(status_code=403, detail="Report access requires a management role")
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
    if not _.is_superuser:
        employee = await get_current_employee(_, session)
        if employee.role == "ORGANIZATION_OWNER":
            pass
        elif employee.role == "HR_ADMIN":
            if employee.unit_id is None:
                raise HTTPException(status_code=403, detail="HR administrator is not assigned to a unit")
            unit_id, department_id = employee.unit_id, None
        elif employee.role == "DEPARTMENT_MANAGER":
            if employee.department_id is None:
                raise HTTPException(status_code=403, detail="Department manager is not assigned to a department")
            unit_id, department_id = None, employee.department_id
        else:
            raise HTTPException(status_code=403, detail="Report access requires a management role")
    service = ReportService(session)
    return await service.get_leave_balance_summary(
        year=year,
        unit_id=unit_id,
        department_id=department_id,
    )
