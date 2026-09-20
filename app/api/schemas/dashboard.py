from pydantic import BaseModel, ConfigDict


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
