export type WorkArrangementType = 'WORK_FROM_HOME' | 'OUT_DUTY' | 'FIELD_WORK' | 'OFFICE'

export interface WorkArrangement {
  id: number
  employee_id: number
  employee_name?: string | null
  employee_code?: string | null
  arrangement_type: WorkArrangementType
  from_date: string
  to_date: string
  reason: string
  destination_location?: string | null
  contact_phone?: string | null
  status: string
  actioned_by?: number | null
  actioned_at?: string | null
  rejection_reason?: string | null
  created_at: string
}
