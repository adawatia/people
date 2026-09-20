export interface LeaveBalance {
  employee_id: number
  leave_type_id: number
  leave_type_name: string
  leave_type_code: string
  leave_period_id?: number | null
  allocated: number
  used: number
  pending: number
  available: number
}

export interface LeaveType {
  id: number
  name: string
  code: string
  is_paid: boolean
  annual_allocation: number
  max_consecutive_days?: number | null
  requires_approval: boolean
  carry_forward: boolean
  include_holidays: boolean
  is_active: boolean
}

export interface LeaveApplication {
  id: number
  employee_id: number
  leave_type_id: number
  leave_period_id?: number | null
  leave_type_name?: string | null
  leave_type_code?: string | null
  employee_name?: string | null
  employee_code?: string | null
  from_date: string
  to_date: string
  half_day: boolean
  half_day_date?: string | null
  days_count: number
  reason?: string | null
  status: string
  applied_at: string
  rejection_reason?: string | null
}
