export interface OvertimeRecord {
  id: number
  employee_id: number
  employee_name?: string | null
  employee_code?: string | null
  attendance_date?: string | null
  attendance_record_id: number
  calculated_minutes: number
  approved_minutes: number
  status: string
  actioned_by?: number | null
  actioned_at?: string | null
  rejection_reason?: string | null
  overtime_start?: string | null
  overtime_end?: string | null
}

export interface OvertimePage {
  items: OvertimeRecord[]
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

export interface OvertimeSummary {
  employee_id: number
  month: number
  year: number
  total_calculated_minutes: number
  total_approved_minutes: number
  pending_count: number
}
