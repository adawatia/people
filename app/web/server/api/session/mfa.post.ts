import type { CurrentUser } from '#shared/types/auth'
import { apiUrl, setAccessCookie, setRefreshCookie, upstreamError } from '../../utils/hrms'

interface UpstreamLoginResponse {
  access_token?: string | null
  refresh_token?: string | null
  expires_in?: number | null
  absolute_expires_at?: string | null
}

interface MfaVerifyPayload {
  mfa_token: string
  code: string
  /** `true` when completing first-time enrolment (`/auth/mfa/activate`). */
  enrollment?: boolean
}

/**
 * Finish a second-factor challenge: verify a TOTP/recovery code (or confirm a
 * brand-new authenticator) and store the issued session.
 *
 * The challenge token comes from `/api/session/login`, so this endpoint alone
 * cannot begin a session — possession of the password is still required.
 */
export default defineEventHandler(async (event): Promise<CurrentUser> => {
  const payload = await readBody<MfaVerifyPayload>(event)
  if (!payload.mfa_token || !payload.code?.trim()) {
    throw createError({ statusCode: 400, statusMessage: 'Enter the code from your authenticator app.' })
  }

  try {
    const path = payload.enrollment ? 'auth/mfa/activate' : 'auth/mfa/verify'
    const auth = await $fetch<UpstreamLoginResponse>(apiUrl(event, path), {
      method: 'POST',
      body: { mfa_token: payload.mfa_token, code: payload.code.trim() }
    })
    if (!auth.access_token) {
      throw createError({ statusCode: 502, statusMessage: 'The HRMS service did not return a session.' })
    }
    setAccessCookie(event, auth.access_token, auth.expires_in)
    if (auth.refresh_token) setRefreshCookie(event, auth.refresh_token, auth.absolute_expires_at)
    return await $fetch<CurrentUser>(apiUrl(event, 'users/me'), {
      headers: { Authorization: `Bearer ${auth.access_token}` }
    })
  } catch (error) {
    throw upstreamError(error)
  }
})
