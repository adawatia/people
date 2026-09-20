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
  currentShift?: string | null
  monthlyPresent: number
  monthlyAbsent: number
  monthlyLeave: number
  overtimeHours: number
  leaveBalances: Array<{ type: string, available: number, used: number, code?: string | null }>
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
