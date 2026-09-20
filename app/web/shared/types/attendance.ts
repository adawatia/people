export type AttendanceStatus
  = | 'PRESENT'
    | 'ABSENT'
    | 'HALF_DAY'
    | 'ON_LEAVE'
    | 'HOLIDAY'
    | 'WEEKLY_OFF'
    | 'MISSED_PUNCH'
    | 'WORK_FROM_HOME'

export interface AttendanceRecord {
  id: number
  employee_id: number
  attendance_date: string
  shift_id?: number | null
  status: AttendanceStatus | string
  punch_in?: string | null
  punch_out?: string | null
  worked_minutes: number
  overtime_minutes: number
  late_minutes: number
  early_exit_minutes: number
}

export interface AttendanceSummary {
  employee_id: number
  month: number
  year: number
  total_working_days: number
  total_present: number
  total_absent: number
  total_leave: number
  total_half_day: number
  total_holiday: number
  total_weekly_off: number
  total_late: number
  total_early_exit: number
  total_missed_punch: number
  total_overtime_minutes: number
  attendance_percentage: number
}

export interface AttendancePunch {
  id: number
  employee_id: number
  punch_time: string
  punch_type: 'IN' | 'OUT'
  source: string
  latitude?: number | null
  longitude?: number | null
  is_processed: boolean
}

export interface AttendanceCorrection {
  id: number
  attendance_record_id: number
  requested_punch_in?: string | null
  requested_punch_out?: string | null
  reason: string
  status: string
  requested_at?: string | null
  rejection_reason?: string | null
}
