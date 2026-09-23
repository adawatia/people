import { checkRequestOrigin, isStateChangingMethod } from '../utils/origin'

/**
 * CSRF guard for the BFF: reject state-changing requests whose declared origin
 * is not this application.
 *
 * This is intentionally separate from CORS (an API concern) — the BFF is
 * same-origin with the browser, and this middleware exists because the session
 * travels in cookies.
 */
export default defineEventHandler((event) => {
  if (!isStateChangingMethod(getMethod(event))) return

  const result = checkRequestOrigin({
    origin: getRequestHeader(event, 'origin'),
    referer: getRequestHeader(event, 'referer'),
    host: getRequestHeader(event, 'host'),
    forwardedHost: getRequestHeader(event, 'x-forwarded-host'),
    allowedOrigins: useRuntimeConfig(event).hrmsAllowedOrigins
  })
  if (result.allowed) return

  // Never reached a handler, so the API was not called: nothing was mutated.
  throw createError({
    statusCode: 403,
    statusMessage: 'This request came from an unexpected origin and was blocked.'
  })
})
