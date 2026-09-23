import type { CurrentUser } from '#shared/types/auth'
import {
  apiUrl,
  clearSessionCookies,
  REFRESH_COOKIE,
  refreshSession,
  SESSION_COOKIE,
  setAccessCookie,
  setRefreshCookie,
  upstreamError,
  upstreamStatus
} from '../../utils/hrms'

/**
 * The signed-in user's effective authorization context (identity, business role,
 * permissions, scope). Authentication here is cookie-based, so an expired access
 * token is refreshed once before giving up — otherwise every session would end
 * after 15 minutes even though the refresh cookie is still valid.
 */
export default defineEventHandler(async (event): Promise<CurrentUser> => {
  const fetchUser = (token: string) => $fetch<CurrentUser>(apiUrl(event, 'users/me'), {
    headers: { Authorization: `Bearer ${token}` }
  })

  const token = getCookie(event, SESSION_COOKIE)
  if (!token) throw createError({ statusCode: 401, statusMessage: 'Your session has expired.' })

  try {
    return await fetchUser(token)
  } catch (error) {
    const status = upstreamStatus(error)
    const refresh = getCookie(event, REFRESH_COOKIE)
    if (status !== 401 || !refresh) {
      if (status === 401) clearSessionCookies(event)
      throw upstreamError(error)
    }
    try {
      const refreshed = await refreshSession(event, refresh)
      setAccessCookie(event, refreshed.access_token, refreshed.expires_in)
      setRefreshCookie(event, refreshed.refresh_token, refreshed.absolute_expires_at)
      return await fetchUser(refreshed.access_token)
    } catch {
      clearSessionCookies(event)
      throw createError({ statusCode: 401, statusMessage: 'Your session has expired. Please sign in again.' })
    }
  }
})
