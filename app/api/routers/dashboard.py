"""routers/dashboard.py — Dynamic permission-based dashboard widget API."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.audit import record_audit_event
from core.auth import fastapi_users, get_user_permissions
from core.database import get_async_session
from core.rbac import get_visible_widgets
from db.models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    Employee,
    LeaveApplication,
    LeaveBalance,
    OvertimeRecord,
    User,
    WorkArrangementRequest,
    now_ist,
)
from schemas.dashboard import (
    DashboardMetricsResponse,
    DashboardWidgetsResponse,
    OwnerDashboardResponse,
    OwnerExceptionResponse,
    TechnicalAdminMetrics,
)
from services.owner_dashboard_service import OwnerDashboardService
from services.shift_service import ShiftService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
PENDING_LEAVE_STATUSES = ("PENDING", "CANCELLATION_PENDING")


def _audit_request_values(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("x-request-id"), request.client.host if request.client else None


def _dashboard_shift(window) -> dict[str, object] | None:
    """Convert a shift window to the narrow, employee-safe dashboard projection."""
    if window is None:
        return None
    return {
        "name": window.shift_name,
        "shiftDate": window.shift_start.date(),
        "startsAt": window.shift_start,
        "endsAt": window.shift_end,
        "isCrossMidnight": window.is_cross_midnight,
    }


@router.get("/owner", response_model=OwnerDashboardResponse, summary="Organization owner analytics dashboard")
async def get_owner_dashboard(
    request: Request,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    unit_id: int | None = Query(None),
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> OwnerDashboardResponse:
    if "dashboard.view_organization" not in await get_user_permissions(user, session):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Organization owner analytics access required")
    payload = await OwnerDashboardService(session).dashboard(from_date, to_date, unit_id)
    request_id, ip_address = _audit_request_values(request)
    await record_audit_event(
        session,
        actor=user,
        action="ORGANIZATION_DASHBOARD_VIEWED",
        entity_type="organization_dashboard",
        filters={"from_date": payload.from_date, "to_date": payload.to_date, "unit_id": unit_id},
        request_id=request_id,
        ip_address=ip_address,
    )
    return payload


@router.get("/owner/exceptions", response_model=OwnerExceptionResponse, summary="Organization owner exception drill-down")
async def get_owner_exceptions(
    request: Request,
    kind: str = Query(...),
    target_date: date = Query(default_factory=date.today),
    unit_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> OwnerExceptionResponse:
    if "dashboard.view_organization" not in await get_user_permissions(user, session):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Organization owner analytics access required")
    payload = await OwnerDashboardService(session).exceptions(kind, unit_id, target_date, page, page_size)
    request_id, ip_address = _audit_request_values(request)
    await record_audit_event(
        session,
        actor=user,
        action="ORGANIZATION_EXCEPTION_DRILLDOWN_VIEWED",
        entity_type="employee_directory",
        filters={"kind": kind, "target_date": target_date, "unit_id": unit_id, "page": page},
        request_id=request_id,
        ip_address=ip_address,
    )
    return payload


@router.get("/technical-metrics", response_model=TechnicalAdminMetrics, summary="Get technical administration counts")
async def get_technical_metrics(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> TechnicalAdminMetrics:
    if not user.is_superuser:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Technical administrator access required")
    from db.models import Department, Designation, Unit
    return TechnicalAdminMetrics(
        users=await session.scalar(select(func.count(User.id)).where(User.is_superuser.is_(False))) or 0,
        employees=await session.scalar(select(func.count(Employee.id)).where(Employee.status == "ACTIVE")) or 0,
        units=await session.scalar(select(func.count(Unit.id)).where(Unit.is_active.is_(True))) or 0,
        departments=await session.scalar(select(func.count(Department.id)).where(Department.is_active.is_(True))) or 0,
        designations=await session.scalar(select(func.count(Designation.id)).where(Designation.is_active.is_(True))) or 0,
    )


@router.get(
    "/widgets",
    response_model=DashboardWidgetsResponse,
    summary="Get dashboard widgets visible to the current user",
)
async def get_dashboard_widgets(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> DashboardWidgetsResponse:
    widgets = await get_visible_widgets(user, session)
    return DashboardWidgetsResponse(widgets=widgets)


@router.get(
    "/metrics",
    response_model=DashboardMetricsResponse,
    summary="Get aggregated KPIs and metrics for the dashboard",
)
async def get_dashboard_metrics(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> DashboardMetricsResponse:
    today = now_ist().date()
    yr = today.year
    mo = today.month

    # Defaults
    unit_metrics = {
        "totalHeadcount": 0,
        "presentCount": 0,
        "absentCount": 0,
        "leaveCount": 0,
        "weeklyOffCount": 0,
        "attendanceRate": 0.0,
        "missedPunches": 0,
        "pendingCorrections": 0,
        "pendingLeaves": 0,
        "todayOvertimeHours": 0,
        "monthlyOvertimeHours": 0
    }

    employee_metrics = {
        "todayStatus": "ABSENT",
        "punchIn": None,
        "punchOut": None,
        "currentShift": None,
        "upcomingShift": None,
        "monthlyPresent": 0,
        "monthlyAbsent": 0,
        "monthlyLeave": 0,
        "monthlyHoliday": 0,
        "overtimeHours": 0,
        "leaveBalances": []
    }

    pending_approvals = []

    # Get employee record for the current user
    emp = (await session.execute(
        select(Employee).options(selectinload(Employee.shift)).where(Employee.user_id == user.id)
    )).scalar_one_or_none()

    # Check if user has manager, HR, or admin privileges
    user_perms = set(await get_user_permissions(user, session))
    has_mgr_access = (
        user.is_super_admin
        or user.is_superuser
        or "leave.approve" in user_perms
        or "employee.view" in user_perms
    )

    if has_mgr_access:
        has_org_scope = user.is_superuser
        unit_scope_ids = [emp.unit_id] if emp and emp.role == "HR_ADMIN" and emp.unit_id else []
        dept_scope_ids = [emp.department_id] if emp and emp.role == "DEPARTMENT_MANAGER" and emp.department_id else []

        if not has_org_scope and not unit_scope_ids and not dept_scope_ids and emp:
            if emp.unit_id:
                unit_scope_ids = [emp.unit_id]
            if emp.department_id:
                dept_scope_ids = [emp.department_id]

        # 1. Total Headcount
        headcount_stmt = select(func.count()).select_from(Employee).where(Employee.status == 'ACTIVE')
        if not has_org_scope:
            if unit_scope_ids:
                headcount_stmt = headcount_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                headcount_stmt = headcount_stmt.where(Employee.department_id.in_(dept_scope_ids))
        unit_metrics["totalHeadcount"] = (await session.scalar(headcount_stmt)) or 0

        # 2. Today's Attendance breakdown
        att_stmt = (
            select(AttendanceRecord.status, func.count(AttendanceRecord.id))
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(AttendanceRecord.attendance_date == today)
        )
        if not has_org_scope:
            if unit_scope_ids:
                att_stmt = att_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                att_stmt = att_stmt.where(Employee.department_id.in_(dept_scope_ids))
        att_stmt = att_stmt.group_by(AttendanceRecord.status)
        att_counts = (await session.execute(att_stmt)).all()
        for status_name, count in att_counts:
            if status_name == "PRESENT": unit_metrics["presentCount"] += count
            elif status_name == "ABSENT": unit_metrics["absentCount"] += count
            elif status_name == "ON_LEAVE": unit_metrics["leaveCount"] += count
            elif status_name == "WEEKLY_OFF": unit_metrics["weeklyOffCount"] += count
            elif status_name == "MISSED_PUNCH": unit_metrics["missedPunches"] += count

        # 3. Attendance Rate
        total_working = unit_metrics["totalHeadcount"] - unit_metrics["leaveCount"] - unit_metrics["weeklyOffCount"]
        if total_working > 0:
            unit_metrics["attendanceRate"] = round((unit_metrics["presentCount"] / total_working) * 100, 1)

        # 4. Overtime hours (Today & Month)
        today_ot_stmt = (
            select(func.sum(OvertimeRecord.approved_minutes))
            .join(AttendanceRecord, OvertimeRecord.attendance_record_id == AttendanceRecord.id)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(AttendanceRecord.attendance_date == today)
        )
        monthly_ot_stmt = (
            select(func.sum(OvertimeRecord.approved_minutes))
            .join(AttendanceRecord, OvertimeRecord.attendance_record_id == AttendanceRecord.id)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(
                func.extract('month', AttendanceRecord.attendance_date) == mo,
                func.extract('year', AttendanceRecord.attendance_date) == yr,
            )
        )
        if not has_org_scope:
            if unit_scope_ids:
                today_ot_stmt = today_ot_stmt.where(Employee.unit_id.in_(unit_scope_ids))
                monthly_ot_stmt = monthly_ot_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                today_ot_stmt = today_ot_stmt.where(Employee.department_id.in_(dept_scope_ids))
                monthly_ot_stmt = monthly_ot_stmt.where(Employee.department_id.in_(dept_scope_ids))

        today_ot = await session.scalar(today_ot_stmt)
        if today_ot:
            unit_metrics["todayOvertimeHours"] = round(today_ot / 60, 1)

        monthly_ot = await session.scalar(monthly_ot_stmt)
        if monthly_ot:
            unit_metrics["monthlyOvertimeHours"] = round(monthly_ot / 60, 1)

        # 5. Pending Approvals Counts (excluding self)
        pending_leaves_stmt = (
            select(func.count())
            .select_from(LeaveApplication)
            .join(Employee, LeaveApplication.employee_id == Employee.id)
            .where(LeaveApplication.status.in_(PENDING_LEAVE_STATUSES))
        )
        pending_corr_stmt = (
            select(func.count())
            .select_from(AttendanceCorrectionRequest)
            .join(AttendanceRecord, AttendanceCorrectionRequest.attendance_record_id == AttendanceRecord.id)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(AttendanceCorrectionRequest.status == 'PENDING')
        )
        if emp:
            pending_leaves_stmt = pending_leaves_stmt.where(LeaveApplication.employee_id != emp.id)
            pending_corr_stmt = pending_corr_stmt.where(AttendanceRecord.employee_id != emp.id)
        if not has_org_scope:
            if unit_scope_ids:
                pending_leaves_stmt = pending_leaves_stmt.where(Employee.unit_id.in_(unit_scope_ids))
                pending_corr_stmt = pending_corr_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                pending_leaves_stmt = pending_leaves_stmt.where(Employee.department_id.in_(dept_scope_ids))
                pending_corr_stmt = pending_corr_stmt.where(Employee.department_id.in_(dept_scope_ids))

        unit_metrics["pendingLeaves"] = (await session.scalar(pending_leaves_stmt)) or 0
        unit_metrics["pendingCorrections"] = (await session.scalar(pending_corr_stmt)) or 0

        # 6. Fetch recent pending leave approvals (excluding self)
        leaves_stmt = (
            select(LeaveApplication)
            .join(Employee, LeaveApplication.employee_id == Employee.id)
            .options(
                selectinload(LeaveApplication.employee).selectinload(Employee.department),
                selectinload(LeaveApplication.leave_type),
            )
            .where(LeaveApplication.status.in_(PENDING_LEAVE_STATUSES))
        )
        if emp:
            leaves_stmt = leaves_stmt.where(LeaveApplication.employee_id != emp.id)
        if not has_org_scope:
            if unit_scope_ids:
                leaves_stmt = leaves_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                leaves_stmt = leaves_stmt.where(Employee.department_id.in_(dept_scope_ids))
        leaves_q = (await session.execute(
            leaves_stmt.order_by(LeaveApplication.applied_at.desc()).limit(5)
        )).scalars().all()

        for l in leaves_q:
            emp_name = f"{l.employee.first_name} {l.employee.last_name or ''}".strip() if l.employee else ""
            dept_name = l.employee.department.name if (l.employee and l.employee.department) else "General"
            pending_approvals.append({
                "id": f"leave_{l.id}",
                "type": "leave_cancellation" if l.status == "CANCELLATION_PENDING" else "leave",
                "employeeName": emp_name or (l.employee.employee_code if l.employee else "Unknown"),
                "employeeCode": l.employee.employee_code if l.employee else "",
                "department": dept_name,
                "detail": (
                    f"Early return from {l.cancellation_effective_date}"
                    if l.status == "CANCELLATION_PENDING"
                    else f"{l.leave_type.name} ({l.days_count} days)" if l.leave_type else f"{l.days_count} days"
                ),
                "timeAgo": l.applied_at.strftime("%b %d, %H:%M") if l.applied_at else "",
            })

        # 7. Fetch recent pending attendance correction approvals (excluding self)
        corrections_stmt = (
            select(AttendanceCorrectionRequest)
            .join(AttendanceRecord, AttendanceCorrectionRequest.attendance_record_id == AttendanceRecord.id)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .options(
                selectinload(AttendanceCorrectionRequest.attendance_record)
                .selectinload(AttendanceRecord.employee)
                .selectinload(Employee.department),
            )
            .where(AttendanceCorrectionRequest.status == 'PENDING')
        )
        if emp:
            corrections_stmt = corrections_stmt.where(AttendanceRecord.employee_id != emp.id)
        if not has_org_scope:
            if unit_scope_ids:
                corrections_stmt = corrections_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                corrections_stmt = corrections_stmt.where(Employee.department_id.in_(dept_scope_ids))
        corrections_q = (await session.execute(
            corrections_stmt.order_by(AttendanceCorrectionRequest.requested_at.desc()).limit(5)
        )).scalars().all()

        for c in corrections_q:
            c_emp = c.attendance_record.employee if c.attendance_record else None
            emp_name = f"{c_emp.first_name} {c_emp.last_name or ''}".strip() if c_emp else ""
            dept_name = c_emp.department.name if (c_emp and c_emp.department) else "General"
            p_in = c.requested_punch_in.strftime("%H:%M") if c.requested_punch_in else "--"
            p_out = c.requested_punch_out.strftime("%H:%M") if c.requested_punch_out else "--"
            pending_approvals.append({
                "id": f"correction_{c.id}",
                "type": "correction",
                "employeeName": emp_name or (c_emp.employee_code if c_emp else "Unknown"),
                "employeeCode": c_emp.employee_code if c_emp else "",
                "department": dept_name,
                "detail": f"Correction ({p_in} - {p_out})",
                "timeAgo": c.requested_at.strftime("%b %d, %H:%M") if c.requested_at else "",
            })

        # 8. Fetch recent pending overtime requests (excluding self)
        ot_stmt = (
            select(OvertimeRecord)
            .join(Employee, OvertimeRecord.employee_id == Employee.id)
            .options(
                selectinload(OvertimeRecord.employee).selectinload(Employee.department)
            )
            .where(OvertimeRecord.status == 'PENDING')
        )
        if emp:
            ot_stmt = ot_stmt.where(OvertimeRecord.employee_id != emp.id)
        if not has_org_scope:
            if unit_scope_ids:
                ot_stmt = ot_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                ot_stmt = ot_stmt.where(Employee.department_id.in_(dept_scope_ids))
        ot_q = (await session.execute(
            ot_stmt.order_by(OvertimeRecord.id.desc()).limit(5)
        )).scalars().all()

        for ot in ot_q:
            o_emp = ot.employee
            emp_name = f"{o_emp.first_name} {o_emp.last_name or ''}".strip() if o_emp else ""
            dept_name = o_emp.department.name if (o_emp and o_emp.department) else "General"
            pending_approvals.append({
                "id": f"overtime_{ot.id}",
                "type": "overtime",
                "employeeName": emp_name or (o_emp.employee_code if o_emp else "Unknown"),
                "employeeCode": o_emp.employee_code if o_emp else "",
                "department": dept_name,
                "detail": f"Overtime ({ot.calculated_minutes} mins)",
                "timeAgo": "",
            })

        # 9. Fetch recent pending work arrangement requests (excluding self)
        wa_stmt = (
            select(WorkArrangementRequest)
            .join(Employee, WorkArrangementRequest.employee_id == Employee.id)
            .options(
                selectinload(WorkArrangementRequest.employee).selectinload(Employee.department)
            )
            .where(WorkArrangementRequest.status == 'PENDING')
        )
        if emp:
            wa_stmt = wa_stmt.where(WorkArrangementRequest.employee_id != emp.id)
        if not has_org_scope:
            if unit_scope_ids:
                wa_stmt = wa_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                wa_stmt = wa_stmt.where(Employee.department_id.in_(dept_scope_ids))
        wa_q = (await session.execute(
            wa_stmt.order_by(WorkArrangementRequest.created_at.desc()).limit(5)
        )).scalars().all()

        for wa in wa_q:
            w_emp = wa.employee
            emp_name = f"{w_emp.first_name} {w_emp.last_name or ''}".strip() if w_emp else ""
            dept_name = w_emp.department.name if (w_emp and w_emp.department) else "General"
            pending_approvals.append({
                "id": f"arrangement_{wa.id}",
                "type": "work_arrangement",
                "employeeName": emp_name or (w_emp.employee_code if w_emp else "Unknown"),
                "employeeCode": w_emp.employee_code if w_emp else "",
                "department": dept_name,
                "detail": f"{wa.arrangement_type} ({wa.from_date} to {wa.to_date})",
                "timeAgo": wa.created_at.strftime("%b %d, %H:%M") if wa.created_at else "",
            })


    if emp:
        # An employee sees only their own effective assignment.  The dated
        # assignment wins over the ERP default shift, including for a future
        # upcoming schedule change. One batched schedule call covers both the
        # today window and the upcoming search.
        shift_schedule = await ShiftService(session).get_employee_shift_schedule(emp.id, now_ist())
        employee_metrics["currentShift"] = _dashboard_shift(shift_schedule.assigned_shift)
        employee_metrics["upcomingShift"] = _dashboard_shift(shift_schedule.upcoming_shift)

        # Today's attendance
        today_att = (await session.execute(
            select(AttendanceRecord).where(AttendanceRecord.employee_id == emp.id, AttendanceRecord.attendance_date == today)
        )).scalar_one_or_none()
        if today_att:
            employee_metrics["todayStatus"] = today_att.status
            employee_metrics["punchIn"] = today_att.punch_in.strftime("%I:%M %p") if today_att.punch_in else None
            employee_metrics["punchOut"] = today_att.punch_out.strftime("%I:%M %p") if today_att.punch_out else None
        
        # Monthly attendance
        mo_att_counts = (await session.execute(
            select(AttendanceRecord.status, func.count(AttendanceRecord.id))
            .where(
                AttendanceRecord.employee_id == emp.id,
                func.extract('month', AttendanceRecord.attendance_date) == mo,
                func.extract('year', AttendanceRecord.attendance_date) == yr
            )
            .group_by(AttendanceRecord.status)
        )).all()
        for status, count in mo_att_counts:
            if status == "PRESENT": employee_metrics["monthlyPresent"] += count
            elif status == "ABSENT": employee_metrics["monthlyAbsent"] += count
            elif status == "ON_LEAVE": employee_metrics["monthlyLeave"] += count
            elif status == "HOLIDAY": employee_metrics["monthlyHoliday"] += count

        # Overtime (monthly)
        mo_ot = (await session.execute(
            select(func.sum(OvertimeRecord.approved_minutes))
            .join(AttendanceRecord)
            .where(
                OvertimeRecord.employee_id == emp.id,
                func.extract('month', AttendanceRecord.attendance_date) == mo,
                func.extract('year', AttendanceRecord.attendance_date) == yr
            )
        )).scalar()
        if mo_ot:
            employee_metrics["overtimeHours"] = round(mo_ot / 60, 1)

        balances_q = (await session.execute(
            select(LeaveBalance)
            .where(LeaveBalance.employee_id == emp.id, LeaveBalance.year == yr)
        )).scalars().all()
        # Fetch leave type names separately to avoid lazy-load
        from db.models import LeaveType as LT
        lt_ids = [b.leave_type_id for b in balances_q]
        lt_map: dict[int, object] = {}
        if lt_ids:
            lt_results = (await session.execute(select(LT).where(LT.id.in_(lt_ids)))).scalars().all()
            lt_map = {lt.id: lt for lt in lt_results}
        for b in balances_q:
            lt = lt_map.get(b.leave_type_id)
            employee_metrics["leaveBalances"].append({
                "type": lt.name if lt else str(b.leave_type_id),
                "available": b.allocated - b.used - b.pending,
                "used": b.used,
                "code": lt.code if lt else "",
                "color": "primary" if (lt and lt.is_paid) else "neutral"
            })

    return {
        "unitMetrics": unit_metrics,
        "employeeMetrics": employee_metrics,
        "pendingApprovals": pending_approvals
    }
