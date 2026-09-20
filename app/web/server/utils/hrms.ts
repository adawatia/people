import type { H3Event } from 'h3'

export const SESSION_COOKIE = 'people_session'
export const REFRESH_COOKIE = 'people_refresh'

export function apiUrl(event: H3Event, path: string) {
  const base = useRuntimeConfig(event).hrmsApiBase.replace(/\/$/, '')
  return `${base}/api/v1/${path.replace(/^\//, '')}`
}

export function sessionToken(event: H3Event) {
  return getCookie(event, SESSION_COOKIE)
}

export function authHeaders(event: H3Event) {
  const token = sessionToken(event)
  if (!token) throw createError({ statusCode: 401, statusMessage: 'Your session has expired.' })
  return { Authorization: `Bearer ${token}` }
}

export function upstreamError(error: unknown) {
  const candidate = error as { statusCode?: number, status?: number, data?: { detail?: unknown }, message?: string }
  const detail = candidate.data?.detail
  const message = typeof detail === 'string'
    ? detail
    : (typeof detail === 'object' && detail && 'reason' in detail ? String((detail as { reason: unknown }).reason) : candidate.message)
  return createError({
    statusCode: candidate.statusCode || candidate.status || 502,
    statusMessage: message || 'The HRMS service could not complete this request.',
    data: candidate.data
  })
}
