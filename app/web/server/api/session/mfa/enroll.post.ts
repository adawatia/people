import type { MfaEnrollment } from '#shared/types/auth'
import { apiUrl, upstreamError } from '../../../utils/hrms'

/**
 * Start first-time MFA enrolment for the account named by a login challenge.
 *
 * Deliberately reachable *only* with a challenge token issued after a correct
 * password, and only while the account has no authenticator — so knowing a
 * password can never be used to replace an enrolled device. The returned secret
 * and recovery codes are shown once and never persisted client-side.
 */
export default defineEventHandler(async (event): Promise<MfaEnrollment> => {
  const payload = await readBody<{ mfa_token?: string }>(event)
  if (!payload.mfa_token) {
    throw createError({ statusCode: 400, statusMessage: 'Sign in again to start setting up an authenticator.' })
  }
  try {
    return await $fetch<MfaEnrollment>(apiUrl(event, 'auth/mfa/enroll'), {
      method: 'POST',
      body: { mfa_token: payload.mfa_token }
    })
  } catch (error) {
    throw upstreamError(error)
  }
})
