import calendar
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import AttendanceRecord, Employee
from repositories.attendance_record_repo import AttendanceRecordRepository
from repositories.employee_repo import EmployeeRepository
from schemas.reports import (
    EmployeeAttendanceRow,
    LeaveBalanceSummaryRow,
    MonthlyAttendanceMatrixReport,
    MonthlyLeaveSummaryReport,
)
from services.leave_service import LeaveService


STATUS_ABBREVIATIONS = {
    "PRESENT": "P",
    "ABSENT": "A",
    "HALF_DAY": "HD",
    "ON_LEAVE": "L",
    "WEEKLY_OFF": "WO",
    "HOLIDAY": "H",
    "WORK_FROM_HOME": "WFH",
    "MISSED_PUNCH": "MP",
}


class ReportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.employee_repo = EmployeeRepository(session)
        self.record_repo = AttendanceRecordRepository(session)
        self.leave_service = LeaveService(session)

    async def get_monthly_attendance_matrix(
        self,
        year: int,
        month: int,
        unit_id: int | None = None,
        department_id: int | None = None,
    ) -> MonthlyAttendanceMatrixReport:
        _, last_day = calendar.monthrange(year, month)
        from_date = date(year, month, 1)
        to_date = date(year, month, last_day)

        # 1. Fetch filtered employees
        stmt = (
            select(Employee)
            .options(selectinload(Employee.department), selectinload(Employee.designation_rel))
            .where(Employee.status == "ACTIVE")
            .order_by(Employee.employee_code)
        )
        if unit_id is not None:
            stmt = stmt.where(Employee.unit_id == unit_id)
        if department_id is not None:
            stmt = stmt.where(Employee.department_id == department_id)

        employees = list((await self.session.execute(stmt)).scalars().all())

        # 2. Fetch all attendance records for these dates
        records_stmt = (
            select(AttendanceRecord)
            .where(
                AttendanceRecord.attendance_date >= from_date,
                AttendanceRecord.attendance_date <= to_date,
            )
        )
        if employees:
            emp_ids = [e.id for e in employees]
            records_stmt = records_stmt.where(AttendanceRecord.employee_id.in_(emp_ids))

        records = list((await self.session.execute(records_stmt)).scalars().all())

        # Group by employee_id -> day_number -> record
        rec_by_emp: dict[int, dict[int, AttendanceRecord]] = {}
        for r in records:
            if r.employee_id not in rec_by_emp:
                rec_by_emp[r.employee_id] = {}
            rec_by_emp[r.employee_id][r.attendance_date.day] = r

        # 3. Build Matrix Rows
        rows: list[EmployeeAttendanceRow] = []
        for emp in employees:
            emp_records = rec_by_emp.get(emp.id, {})
            day_map: dict[int, str] = {}

            p_count = 0
            a_count = 0
            hd_count = 0
            l_count = 0
            wo_count = 0
            h_count = 0
            total_late = 0
            total_ot = 0

            for day in range(1, last_day + 1):
                rec = emp_records.get(day)
                if rec:
                    code = STATUS_ABBREVIATIONS.get(rec.status, rec.status[:2])
                    day_map[day] = code

                    if rec.status == "PRESENT":
                        p_count += 1
                    elif rec.status == "ABSENT":
                        a_count += 1
                    elif rec.status == "HALF_DAY":
                        hd_count += 1
                    elif rec.status == "ON_LEAVE":
                        l_count += 1
                    elif rec.status == "WEEKLY_OFF":
                        wo_count += 1
                    elif rec.status == "HOLIDAY":
                        h_count += 1
                    elif rec.status == "WORK_FROM_HOME":
                        p_count += 1

                    total_late += rec.late_minutes
                    total_ot += rec.overtime_minutes
                else:
                    day_map[day] = "-"

            row = EmployeeAttendanceRow(
                employee_id=emp.id,
                employee_code=emp.employee_code,
                employee_name=f"{emp.first_name} {emp.last_name}",
                department_name=emp.department.name if emp.department else None,
                designation_name=emp.designation_rel.name if emp.designation_rel else emp.designation,
                day_status_map=day_map,
                total_present=p_count,
                total_absent=a_count,
                total_half_day=hd_count,
                total_leave=l_count,
                total_weekly_off=wo_count,
                total_holiday=h_count,
                total_late_minutes=total_late,
                total_overtime_minutes=total_ot,
            )
            rows.append(row)

        return MonthlyAttendanceMatrixReport(
            year=year,
            month=month,
            unit_id=unit_id,
            total_days_in_month=last_day,
            rows=rows,
        )

    async def get_leave_balance_summary(
        self,
        year: int,
        unit_id: int | None = None,
        department_id: int | None = None,
    ) -> MonthlyLeaveSummaryReport:
        stmt = (
            select(Employee)
            .options(selectinload(Employee.department))
            .where(Employee.status == "ACTIVE")
            .order_by(Employee.employee_code)
        )
        if unit_id is not None:
            stmt = stmt.where(Employee.unit_id == unit_id)
        if department_id is not None:
            stmt = stmt.where(Employee.department_id == department_id)

        employees = list((await self.session.execute(stmt)).scalars().all())

        check_date = date(year, 12, 31)
        rows: list[LeaveBalanceSummaryRow] = []

        for emp in employees:
            balances = await self.leave_service.get_employee_leave_balances(emp.id, for_date=check_date)
            for b in balances:
                rows.append(
                    LeaveBalanceSummaryRow(
                        employee_id=emp.id,
                        employee_code=emp.employee_code,
                        employee_name=f"{emp.first_name} {emp.last_name}",
                        department_name=emp.department.name if emp.department else None,
                        leave_type_name=b.leave_type_name,
                        leave_type_code=b.leave_type_code,
                        allocated=b.allocated,
                        used=b.used,
                        pending=b.pending,
                        available=b.available,
                    )
                )

        return MonthlyLeaveSummaryReport(
            year=year,
            unit_id=unit_id,
            rows=rows,
        )
