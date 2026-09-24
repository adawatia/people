
from pydantic import BaseModel

from core.pagination import PaginatedResponse


class EmployeeAttendanceRow(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    department_name: str | None = None
    designation_name: str | None = None
    day_status_map: dict[int, str]  # day number -> status abbreviation ("P", "A", "HD", "L", "WO", "H", "WFH")
    total_present: int = 0
    total_absent: int = 0
    total_half_day: int = 0
    total_leave: int = 0
    total_weekly_off: int = 0
    total_holiday: int = 0
    total_late_minutes: int = 0
    total_overtime_minutes: int = 0


class MonthlyAttendanceMatrixReport(PaginatedResponse[EmployeeAttendanceRow]):
    year: int
    month: int
    unit_id: int | None = None
    total_days_in_month: int
    @property
    def rows(self):
        return self.items


class LeaveBalanceSummaryRow(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    department_name: str | None = None
    leave_type_name: str
    leave_type_code: str
    allocated: float
    used: float
    pending: float
    available: float


class MonthlyLeaveSummaryReport(PaginatedResponse[LeaveBalanceSummaryRow]):
    year: int
    unit_id: int | None = None
    breakdown: list[dict] = []

    @property
    def rows(self):
        return self.items
