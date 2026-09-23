import type { H3Event } from 'h3'

/**
 * Cookie names and BFF plumbing.
 *
 * The browser only ever holds HttpOnly cookies: the access token and the
 * rotating refresh token are never exposed to application JavaScript, so an XSS
 * bug cannot read them.
 *
 * In production the cookies also carry the `__Host-` prefix, which the browser
 * accepts only for a `Secure`, `Path=/`, Domain-less cookie. That makes it
 * impossible for a compromised sibling subdomain to overwrite the session
 * cookie. Development runs over plain HTTP on localhost, where the prefix (and
 * `Secure`) cannot be applied, so the plain names are used there — the two
 * environments are deliberately keyed off `import.meta.dev`.
 */
const cookiePrefix = import.meta.dev ? '' : '__Host-'
export const SESSION_COOKIE = `${cookiePrefix}people_session`
export const REFRESH_COOKIE = `${cookiePrefix}people_refresh`

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

/** Shared attributes: HttpOnly, Secure outside development, SameSite=Lax, Path=/. */
function baseCookieOptions() {
  return {
    httpOnly: true,
    secure: !import.meta.dev,
    sameSite: 'lax' as const,
    path: '/'
  }
}

/**
 * Store the access token for exactly as long as the server considers it valid.
 * The cookie is a transport detail — authorization is always re-checked
 * server-side, and the API rejects an expired token regardless of the cookie.
 */
export function setAccessCookie(event: H3Event, token: string, expiresInSeconds?: number | null) {
  setCookie(event, SESSION_COOKIE, token, {
    ...baseCookieOptions(),
    maxAge: Math.max(60, Math.floor(expiresInSeconds ?? 900))
  })
}

/**
 * Store the refresh token, expiring the cookie no later than the session's hard
 * end. Browser cookie expiry is never the revocation mechanism — it only avoids
 * sending a token the server has already been told is worthless.
 */
export function setRefreshCookie(event: H3Event, token: string, absoluteExpiresAt?: string | null) {
  const deadline = absoluteExpiresAt ? Date.parse(absoluteExpiresAt) : Number.NaN
  const maxAge = Number.isFinite(deadline)
    ? Math.max(60, Math.floor((deadline - Date.now()) / 1000))
    : 60 * 60 * 24 * 30
  setCookie(event, REFRESH_COOKIE, token, { ...baseCookieOptions(), maxAge })
}

export function clearSessionCookies(event: H3Event) {
  deleteCookie(event, SESSION_COOKIE, { path: '/' })
  deleteCookie(event, REFRESH_COOKIE, { path: '/' })
}

export interface RefreshedSession {
  access_token: string
  refresh_token: string
  expires_in: number
  absolute_expires_at?: string | null
}

/**
 * In-flight refreshes, keyed by the refresh token being exchanged.
 *
 * A page that fires several API calls at once must not rotate the same refresh
 * token concurrently: the backend correctly treats the second use as replay and
 * revokes the whole session chain. So concurrent callers share one rotation and
 * all apply the same resulting cookies.
 */
const inFlightRefreshes = new Map<string, Promise<RefreshedSession>>()

export function refreshSession(event: H3Event, refreshToken: string): Promise<RefreshedSession> {
  const existing = inFlightRefreshes.get(refreshToken)
  if (existing) return existing

  const pending = $fetch<RefreshedSession>(apiUrl(event, 'auth/session/refresh'), {
    method: 'POST',
    body: { refresh_token: refreshToken }
  }).finally(() => {
    inFlightRefreshes.delete(refreshToken)
  })

  inFlightRefreshes.set(refreshToken, pending)
  return pending
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

export function upstreamStatus(error: unknown) {
  const candidate = error as { statusCode?: number, status?: number }
  return candidate.statusCode || candidate.status || 502
}
