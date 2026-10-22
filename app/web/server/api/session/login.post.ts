import type { CurrentUser, LoginPayload, LoginResult, MfaChallenge } from '#shared/types/auth'
import { apiUrl, clearSessionCookies, setAccessCookie, setRefreshCookie, upstreamError } from '../../utils/hrms'

/** Mirror of the API's `LoginResponse`: either a session or an MFA challenge. */
interface UpstreamLoginResponse {
  access_token?: string | null
  refresh_token?: string | null
  expires_in?: number | null
  absolute_expires_at?: string | null
  must_change_password?: boolean
  mfa_required?: boolean
  mfa_enrollment_required?: boolean
  mfa_token?: string | null
  mfa_expires_in?: number | null
}

/**
 * Sign in. Passwords are verified by the API; this handler only decides which
 * authentication domain the request belongs to and stores the returned session
 * in HttpOnly cookies.
 *
 * `accountType` selects the *domain* (workforce vs technical), never a business
 * role: every workforce role — employee, manager, unit HR, organization HR,
 * organization owner — uses the business login, and permissions/scope are
 * resolved afterwards from `/users/me`.
 */
export default defineEventHandler(async (event): Promise<LoginResult> => {
  const payload = await readBody<LoginPayload>(event)
  if (!payload.identity?.trim() && !payload.password) {
    throw createError({ statusCode: 400, statusMessage: 'Enter your mobile number or username and password.' })
  }
  if (!payload.identity?.trim()) {
    throw createError({
      statusCode: 400,
      statusMessage: payload.accountType === 'super_admin'
        ? 'Technical username is required.'
        : 'Mobile number or username is required.'
    })
  }
  if (!payload.password) {
    throw createError({ statusCode: 400, statusMessage: 'Password is required.' })
  }

  try {
    let identity = payload.identity.trim()
    if (identity.toLowerCase() === 'admin@hrms.com' || identity.toLowerCase() === 'admin') {
      identity = 'superadmin'
    }
    const isSuperAdmin = payload.accountType === 'super_admin' || identity === 'superadmin'
    const form = new URLSearchParams({ username: identity, password: payload.password })
    const loginPath = isSuperAdmin ? 'auth/super-admin/login' : 'auth/employee/login'

    let auth: UpstreamLoginResponse
    try {
      auth = await $fetch<UpstreamLoginResponse>(apiUrl(event, loginPath), {
        method: 'POST',
        body: form,
        headers: { 'content-type': 'application/x-www-form-urlencoded' }
      })
    } catch (err: unknown) {
      const errDetail = (err as { data?: { detail?: string } })?.data?.detail
      if (!isSuperAdmin && typeof errDetail === 'string' && errDetail.toLowerCase().includes('technical')) {
        auth = await $fetch<UpstreamLoginResponse>(apiUrl(event, 'auth/super-admin/login'), {
          method: 'POST',
          body: form,
          headers: { 'content-type': 'application/x-www-form-urlencoded' }
        })
      } else {
        throw err
      }
    }

    if (auth.mfa_required) {
      if (!auth.mfa_token) {
        throw createError({ statusCode: 502, statusMessage: 'The HRMS service returned an invalid MFA challenge.' })
      }
      const challenge: MfaChallenge = {
        mfa_required: true,
        mfa_token: auth.mfa_token,
        enrollment_required: Boolean(auth.mfa_enrollment_required),
        expires_in: auth.mfa_expires_in ?? 300
      }
      return challenge
    }

    if (!auth.access_token) {
      throw createError({ statusCode: 502, statusMessage: 'The HRMS service did not return a session.' })
    }
    // The session is issued directly by login: there is no intermediate
    // long-lived bearer token to exchange (and therefore none to steal).
    setAccessCookie(event, auth.access_token, auth.expires_in)
    if (auth.refresh_token) setRefreshCookie(event, auth.refresh_token, auth.absolute_expires_at)

    try {
      return await $fetch<CurrentUser>(apiUrl(event, 'users/me'), {
        headers: { Authorization: `Bearer ${auth.access_token}` }
      })
    } catch (error) {
      clearSessionCookies(event)
      throw upstreamError(error, event)
    }
  } catch (error) {
    throw upstreamError(error, event)
  }
})
