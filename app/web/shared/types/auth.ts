export interface RoleAssignment {
  id: number
  role_id: number
  role_name?: string | null
  scope_type: 'organization' | 'unit' | 'department'
  scope_id?: number | null
  assigned_at?: string | null
}

export interface CurrentUser {
  id: number
  email: string
  username: string
  first_name?: string | null
  last_name?: string | null
  mobile_number?: string | null
  is_active: boolean
  is_superuser: boolean
  is_verified: boolean
  must_change_password: boolean
  assignments: RoleAssignment[]
  permissions: string[]
  employee_id?: number | null
  employee_code?: string | null
}

export interface LoginPayload {
  identity: string
  password: string
}
