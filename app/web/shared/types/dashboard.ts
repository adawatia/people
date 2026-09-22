export interface UnitMetrics {
  totalHeadcount: number
  presentCount: number
  absentCount: number
  leaveCount: number
  attendanceRate: number
  missedPunches: number
  pendingCorrections: number
  pendingLeaves: number
}

export interface EmployeeMetrics {
  todayStatus: string
  punchIn?: string | null
  punchOut?: string | null
  currentShift?: EmployeeDashboardShift | null
  upcomingShift?: EmployeeDashboardShift | null
  monthlyPresent: number
  monthlyAbsent: number
  monthlyLeave: number
  overtimeHours: number
  leaveBalances: Array<{ type: string, available: number, used: number, code?: string | null }>
}

export interface EmployeeDashboardShift {
  name: string
  shiftDate: string
  startsAt: string
  endsAt: string
  isCrossMidnight: boolean
}

export interface PendingApproval {
  id: string | number
  type: string
  employeeName?: string | null
  employeeCode?: string | null
  department?: string | null
  detail?: string | null
  timeAgo?: string | null
}

export interface DashboardMetrics {
  unitMetrics: UnitMetrics
  employeeMetrics: EmployeeMetrics
  pendingApprovals: PendingApproval[]
}

export interface OwnerSummary {
  active_headcount: number
  present: number
  absent: number
  on_leave: number
  weekly_off_or_holiday: number
  attendance_rate: number
  late_or_missed_punches: number
  pending_requests: number
  approved_overtime_minutes: number
}

export interface OwnerTrendPoint {
  date: string
  present: number
  absent: number
  on_leave: number
  weekly_off_or_holiday: number
}

export interface OwnerOrgRow {
  id: number
  name: string
  headcount: number
  present: number
  absent: number
  on_leave: number
  exceptions: number
  attendance_rate: number
  approved_overtime_minutes: number
}

export interface OwnerDashboard {
  from_date: string
  to_date: string
  generated_at: string
  attendance_last_synced_at?: string | null
  summary: OwnerSummary
  trend: OwnerTrendPoint[]
  units: OwnerOrgRow[]
  departments: OwnerOrgRow[]
}

export interface OwnerExceptionResponse {
  items: import('./employee').Employee[]
  total: number
  page: number
  page_size: number
  total_pages: number
}
