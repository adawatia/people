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

/**
 * Second factor required: returned by `/api/session/login` instead of a user
 * when the account must prove possession of its authenticator. The challenge
 * token is short-lived and only usable for the MFA endpoints.
 */
export interface MfaChallenge {
  mfa_required: true
  mfa_token: string
  /** First sign-in for this account: an authenticator must be enrolled now. */
  enrollment_required: boolean
  expires_in: number
}

/** Login outcome: a signed-in user, or a second-factor challenge to complete. */
export type LoginResult = CurrentUser | MfaChallenge

/** One-time view of a new authenticator secret; never returned again. */
export interface MfaEnrollment {
  secret: string
  otpauth_uri: string
  recovery_codes: string[]
}

export interface MfaStatus {
  enabled: boolean
  enrolled_at?: string | null
  last_verified_at?: string | null
  recovery_codes_remaining: number
}

/** A signed-in session (device) as reported by `GET /auth/sessions`. */
export interface SessionSummary {
  id: number
  created_at: string
  last_used_at?: string | null
  expires_at: string
  absolute_expires_at: string
  ip_address?: string | null
  user_agent?: string | null
  is_current: boolean
}
