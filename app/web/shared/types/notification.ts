export interface HrmsNotification {
  notification_id: number
  title: string
  message: string
  notification_type: string
  reference_id?: number | null
  reference_type?: string | null
  link?: string | null
  user_id?: number | null
  target_role?: string | null
  is_read: boolean
  created_at: string
}
