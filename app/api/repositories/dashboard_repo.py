"""Dynamic permission-based dashboard widget queries."""

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth import get_user_permissions
from core.employee_access import get_employee_scope
from db.models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    Employee,
    LeaveApplication,
    LeaveBalance,
    LeaveType,
    OvertimeRecord,
    User,
    WorkArrangementRequest,
    now_ist,
)
from schemas.dashboard import (
    DashboardMetricsResponse,
)

PENDING_LEAVE_STATUSES = ("PENDING", "CANCELLATION_PENDING")

async def dashboard_metrics(user: User, session: AsyncSession) -> DashboardMetricsResponse:
    today = now_ist().date()
    yr = today.year
    mo = today.month
    month_start = date(yr, mo, 1)
    next_month = date(yr + 1, 1, 1) if mo == 12 else date(yr, mo + 1, 1)

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
        # Scope always comes from the centralized resolver: unit HR sees their
        # unit, organization HR and the Organization Owner see everything, a
        # department manager sees their department.
        has_org_scope = user.is_superuser
        unit_scope_ids: list[int] = []
        dept_scope_ids: list[int] = []
        if not has_org_scope:
            scope = await get_employee_scope(user, session)
            has_org_scope = scope.organization
            unit_scope_ids = sorted(scope.unit_ids)
            dept_scope_ids = sorted(scope.department_ids)

        if not has_org_scope and not unit_scope_ids and not dept_scope_ids:
            from fastapi import HTTPException
            raise HTTPException(403, "No management scope assigned")

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

        # One date-bounded scan provides both overtime figures.
        overtime_stmt = (
            select(
                func.coalesce(func.sum(case(
                    (AttendanceRecord.attendance_date == today, OvertimeRecord.approved_minutes), else_=0
                )), 0),
                func.coalesce(func.sum(OvertimeRecord.approved_minutes), 0),
            )
            .join(AttendanceRecord, OvertimeRecord.attendance_record_id == AttendanceRecord.id)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(
                AttendanceRecord.attendance_date >= month_start,
                AttendanceRecord.attendance_date < next_month,
            )
        )
        if not has_org_scope:
            if unit_scope_ids:
                overtime_stmt = overtime_stmt.where(Employee.unit_id.in_(unit_scope_ids))
            elif dept_scope_ids:
                overtime_stmt = overtime_stmt.where(Employee.department_id.in_(dept_scope_ids))

        today_ot, monthly_ot = (await session.execute(overtime_stmt)).one()
        if today_ot:
            unit_metrics["todayOvertimeHours"] = round(today_ot / 60, 1)
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


        # A month contains at most 31 rows per employee, including today's row.
        month_records = (await session.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == emp.id,
                AttendanceRecord.attendance_date >= month_start,
                AttendanceRecord.attendance_date < next_month,
            )
        )).all()
        today_att = next((record for record in month_records if record.attendance_date == today), None)
        if today_att:
            employee_metrics["todayStatus"] = today_att.status
            employee_metrics["punchIn"] = today_att.punch_in.strftime("%I:%M %p") if today_att.punch_in else None
            employee_metrics["punchOut"] = today_att.punch_out.strftime("%I:%M %p") if today_att.punch_out else None

        for record in month_records:
            if record.status == "PRESENT": employee_metrics["monthlyPresent"] += 1
            elif record.status == "ABSENT": employee_metrics["monthlyAbsent"] += 1
            elif record.status == "ON_LEAVE": employee_metrics["monthlyLeave"] += 1
            elif record.status == "HOLIDAY": employee_metrics["monthlyHoliday"] += 1

        # Overtime (monthly)
        mo_ot = (await session.execute(
            select(func.sum(OvertimeRecord.approved_minutes))
            .join(AttendanceRecord)
            .where(
                OvertimeRecord.employee_id == emp.id,
                AttendanceRecord.attendance_date >= month_start,
                AttendanceRecord.attendance_date < next_month,
            )
        )).scalar()
        if mo_ot:
            employee_metrics["overtimeHours"] = round(mo_ot / 60, 1)

        balances_q = (await session.execute(
            select(LeaveBalance, LeaveType)
            .outerjoin(LeaveType, LeaveBalance.leave_type_id == LeaveType.id)
            .where(LeaveBalance.employee_id == emp.id, LeaveBalance.year == yr)
        )).all()
        for b, lt in balances_q:
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
