import { apiUrl, clearSessionCookies, REFRESH_COOKIE, upstreamStatus } from '../../utils/hrms'

/**
 * Log out: revoke the server-side session, then clear both cookies.
 *
 * Cookies are always cleared, even when the API call fails — a browser that
 * keeps a dead cookie is worse than one that must sign in again. Idempotent:
 * logging out twice is not an error.
 */
export default defineEventHandler(async (event) => {
  const refresh = getCookie(event, REFRESH_COOKIE)
  if (refresh) {
    try {
      await $fetch(apiUrl(event, 'auth/session'), { method: 'DELETE', body: { refresh_token: refresh } })
    } catch (error) {
      // 404/401 means the session was already gone server-side.
      const status = upstreamStatus(error)
      if (status !== 401 && status !== 404) console.warn('logout: could not revoke upstream session', status)
    }
  }
  clearSessionCookies(event)
  setResponseStatus(event, 204)
  return null
})
