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
 * Authenticated proxy to the HRMS API. The browser never talks to FastAPI
 * directly and never sees a bearer token: this handler attaches the access token
 * from its HttpOnly cookie.
 *
 * When the access token has expired the request is retried once with a rotated
 * session. Rotation is single-flight (`refreshSession`), so a page that issues
 * several calls at once cannot trip the API's replay protection.
 */
export default defineEventHandler(async (event) => {
  const path = getRouterParam(event, 'path') || ''
  const method = getMethod(event)
  const query = getQuery(event)
  const body = ['GET', 'HEAD'].includes(method) ? undefined : await readBody(event)

  const call = (token: string) => $fetch(apiUrl(event, path), {
    method: method as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
    query,
    body,
    retry: 0,
    headers: { Authorization: `Bearer ${token}` }
  })

  const token = getCookie(event, SESSION_COOKIE)
  const refresh = getCookie(event, REFRESH_COOKIE)
  try {
    if (!token) throw createError({ statusCode: 401, statusMessage: 'Access token expired.' })
    return await call(token)
  } catch (error) {
    const status = upstreamStatus(error)
    // The refresh route is itself the recovery path — never recurse into it.
    if (status === 401 && refresh && path !== 'auth/session/refresh') {
      let refreshed
      try {
        refreshed = await refreshSession(event, refresh)
      } catch (refreshError) {
        if ([400, 401, 403].includes(upstreamStatus(refreshError))) clearSessionCookies(event)
        throw upstreamError(refreshError)
      }
      setAccessCookie(event, refreshed.access_token, refreshed.expires_in)
      setRefreshCookie(event, refreshed.refresh_token, refreshed.absolute_expires_at)
      try {
        return await call(refreshed.access_token)
      } catch (retryError) {
        if (upstreamStatus(retryError) === 401) clearSessionCookies(event)
        throw upstreamError(retryError)
      }
    }
    if (status === 401) clearSessionCookies(event)
    throw upstreamError(error)
  }
})
