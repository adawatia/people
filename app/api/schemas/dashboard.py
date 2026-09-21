from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from schemas.employees import EmployeeDirectoryRead


class DashboardWidgetsResponse(BaseModel):
    widgets: list[str]


class UnitMetrics(BaseModel):
    totalHeadcount: int = 0
    presentCount: int = 0
    absentCount: int = 0
    leaveCount: int = 0
    weeklyOffCount: int = 0
    attendanceRate: float = 0.0
    missedPunches: int = 0
    pendingCorrections: int = 0
    pendingLeaves: int = 0
    todayOvertimeHours: float = 0.0
    monthlyOvertimeHours: float = 0.0


class EmployeeDashboardLeaveBalance(BaseModel):
    type: str
    available: float = 0.0
    used: float = 0.0
    code: str | None = None
    color: str | None = None


class EmployeeMetrics(BaseModel):
    todayStatus: str = "ABSENT"
    punchIn: str | None = None
    punchOut: str | None = None
    currentShift: str | None = None
    monthlyPresent: int = 0
    monthlyAbsent: int = 0
    monthlyLeave: int = 0
    monthlyHoliday: int = 0
    overtimeHours: float = 0.0
    leaveBalances: list[EmployeeDashboardLeaveBalance] = []


class PendingApprovalItem(BaseModel):
    id: str | int
    type: str
    employeeName: str | None = None
    employeeCode: str | None = None
    department: str | None = None
    detail: str | None = None
    timeAgo: str | None = None


class DashboardMetricsResponse(BaseModel):
    unitMetrics: UnitMetrics
    employeeMetrics: EmployeeMetrics
    pendingApprovals: list[PendingApprovalItem] = []

    model_config = ConfigDict(from_attributes=True)


class TechnicalAdminMetrics(BaseModel):
    users: int = 0
    employees: int = 0
    units: int = 0
    departments: int = 0
    designations: int = 0


class OwnerSummary(BaseModel):
    active_headcount: int = 0
    present: int = 0
    absent: int = 0
    on_leave: int = 0
    weekly_off_or_holiday: int = 0
    attendance_rate: float = 0.0
    late_or_missed_punches: int = 0
    pending_requests: int = 0
    approved_overtime_minutes: int = 0


class OwnerTrendPoint(BaseModel):
    date: date
    present: int = 0
    absent: int = 0
    on_leave: int = 0
    weekly_off_or_holiday: int = 0


class OwnerOrgRow(BaseModel):
    id: int
    name: str
    headcount: int = 0
    present: int = 0
    absent: int = 0
    on_leave: int = 0
    exceptions: int = 0
    attendance_rate: float = 0.0
    approved_overtime_minutes: int = 0


class OwnerDashboardResponse(BaseModel):
    from_date: date
    to_date: date
    generated_at: datetime
    attendance_last_synced_at: datetime | None = None
    summary: OwnerSummary
    trend: list[OwnerTrendPoint] = Field(default_factory=list)
    units: list[OwnerOrgRow] = Field(default_factory=list)
    departments: list[OwnerOrgRow] = Field(default_factory=list)


class OwnerExceptionResponse(BaseModel):
    items: list[EmployeeDirectoryRead]
    total: int
    page: int
    page_size: int
    total_pages: int
