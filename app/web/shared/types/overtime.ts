export interface OvertimeRecord {
  id: number
  employee_id: number
  attendance_record_id: number
  calculated_minutes: number
  approved_minutes: number
  status: string
  actioned_by?: number | null
  actioned_at?: string | null
  rejection_reason?: string | null
}

export interface OvertimeSummary {
  employee_id: number
  month: number
  year: number
  total_calculated_minutes: number
  total_approved_minutes: number
  pending_count: number
}
