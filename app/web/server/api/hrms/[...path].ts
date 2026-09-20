import { apiUrl, REFRESH_COOKIE, SESSION_COOKIE, upstreamError } from '../../utils/hrms'

export default defineEventHandler(async (event) => {
  const path = getRouterParam(event, 'path') || ''
  const method = getMethod(event)
  const query = getQuery(event)
  const body = ['GET', 'HEAD'].includes(method) ? undefined : await readBody(event)

  const request = (token: string) => $fetch(apiUrl(event, path), {
    method: method as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
    query,
    body,
    headers: { Authorization: `Bearer ${token}` }
  })
  try {
    return await request(getCookie(event, SESSION_COOKIE) || '')
  } catch (error) {
    const status = (error as { statusCode?: number, status?: number }).statusCode || (error as { status?: number }).status
    if (status === 401 && getCookie(event, REFRESH_COOKIE) && path !== 'auth/session/refresh') {
      try {
        const refreshed = await $fetch<{ access_token: string, refresh_token: string }>(apiUrl(event, 'auth/session/refresh'), {
          method: 'POST', body: { refresh_token: getCookie(event, REFRESH_COOKIE) }
        })
        setCookie(event, SESSION_COOKIE, refreshed.access_token, { httpOnly: true, secure: !import.meta.dev, sameSite: 'lax', path: '/', maxAge: 60 * 15 })
        setCookie(event, REFRESH_COOKIE, refreshed.refresh_token, { httpOnly: true, secure: !import.meta.dev, sameSite: 'lax', path: '/', maxAge: 60 * 60 * 24 * 30 })
        return await request(refreshed.access_token)
      } catch { /* fall through and clear both cookies */ }
    }
    if (status === 401) {
      deleteCookie(event, SESSION_COOKIE, { path: '/' })
      deleteCookie(event, REFRESH_COOKIE, { path: '/' })
    }
    throw upstreamError(error)
  }
})
