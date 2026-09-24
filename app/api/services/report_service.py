import calendar
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AttendanceRecord
from repositories.attendance_record_repo import AttendanceRecordRepository
from repositories.employee_repo import EmployeeRepository
from repositories.report_repo import ReportRepository
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
        self.repo = ReportRepository(session)
        self.employee_repo = EmployeeRepository(session)
        self.record_repo = AttendanceRecordRepository(session)
        self.leave_service = LeaveService(session)

    async def get_monthly_attendance_matrix(
        self,
        year: int,
        month: int,
        unit_id: int | None = None,
        department_id: int | None = None,
        page: int = 1, page_size: int = 25, search: str | None = None,
        sort_by: str | None = None, sort_order: str = "asc",
    ) -> MonthlyAttendanceMatrixReport:
        _, last_day = calendar.monthrange(year, month)
        from_date = date(year, month, 1)
        to_date = date(year, month, last_day)

        query = self.repo.employees(unit_id, department_id, search)
        result = await self.repo.employee_page(query, page, page_size, sort_by, sort_order)
        employees = result.pop("items")
        records = await self.repo.attendance([emp.id for emp in employees], from_date, to_date)

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
            items=rows, **result,
        )

    async def get_leave_balance_summary(
        self,
        year: int,
        unit_id: int | None = None,
        department_id: int | None = None,
        page: int = 1, page_size: int = 25, search: str | None = None,
        sort_by: str | None = None, sort_order: str = "asc",
    ) -> MonthlyLeaveSummaryReport:
        query = self.repo.employees(unit_id, department_id, search)
        result = await self.repo.employee_page(query, page, page_size, sort_by, sort_order)
        employees = result.pop("items")
        by_id = {emp.id: emp for emp in employees}
        balances = await self.repo.balances(list(by_id), year)
        rows = []
        for balance in balances:
            emp = by_id[balance.employee_id]
            rows.append(LeaveBalanceSummaryRow(
                employee_id=emp.id, employee_code=emp.employee_code,
                employee_name=f"{emp.first_name} {emp.last_name or ''}".strip(),
                department_name=emp.department.name if emp.department else None,
                leave_type_name=balance.leave_type.name, leave_type_code=balance.leave_type.code,
                allocated=float(balance.allocated), used=float(balance.used), pending=float(balance.pending),
                available=max(0.0, float(balance.allocated - balance.used - balance.pending))))
        totals = await self.repo.balance_totals(query, year)
        return MonthlyLeaveSummaryReport(year=year, unit_id=unit_id, items=rows, breakdown=totals, **result)
