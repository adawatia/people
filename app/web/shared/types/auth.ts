/**
 * Elevated business role. Every employee implicitly holds base self-service
 * access; a business role adds operational capabilities on top.
 */
export type BusinessRole = 'DEPARTMENT_MANAGER' | 'HR_ADMIN' | 'ORGANIZATION_OWNER'

/**
 * Where a business role applies. `SELF` means the employee has no elevation and
 * is limited to their own records. The scope identifier stays server-side: the
 * client only needs the type to adapt copy and layout.
 */
export type AccessScope = 'SELF' | 'DEPARTMENT' | 'UNIT' | 'ORGANIZATION'

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
  /** Compatibility mirror of `business_role`; `SUPER_ADMIN` for technical accounts. */
  role: 'EMPLOYEE' | 'DEPARTMENT_MANAGER' | 'HR_ADMIN' | 'ORGANIZATION_OWNER' | 'SUPER_ADMIN'
  business_role?: BusinessRole | null
  scope_type?: AccessScope
  /** Effective permission codes; the server is the authority for authorization. */
  permissions?: string[]
  employee_id?: number | null
  employee_code?: string | null
}

export interface LoginPayload {
  identity: string
  password: string
  accountType?: 'employee' | 'super_admin'
}
