/**
 * Browser-origin validation for cookie-authenticated state-changing requests.
 *
 * The BFF authenticates the browser with cookies, so a cross-site request would
 * otherwise be sent *with* the user's credentials. `SameSite=Lax` blocks the
 * common cases but is not the whole strategy (older browsers, and top-level
 * navigations, still differ), so mutations additionally require a verified
 * origin.
 *
 * Rules, in order:
 *
 *  1. A declared origin (`Origin`, else the `Referer`'s origin) that matches the
 *     request's own host, or a configured allowed origin, is accepted.
 *  2. A declared origin that matches neither is rejected — this is the CSRF
 *     case.
 *  3. No `Origin` and no `Referer` is accepted: browsers always send `Origin` on
 *     a cross-site state-changing request, so a header-less caller is a
 *     non-browser client (mobile app, CLI, health probe) that carries no ambient
 *     cookie authority to abuse.
 *
 * Comparison is host-based on purpose: the public host is often not the host the
 * BFF sees (TLS terminates upstream), so comparing schemes here would reject
 * legitimate traffic. Deployments whose public origin differs from the request
 * host list it explicitly in `NUXT_HRMS_ALLOWED_ORIGINS`.
 */

export interface OriginCheckInput {
  origin?: string | null
  referer?: string | null
  host?: string | null
  forwardedHost?: string | null
  allowedOrigins?: string[]
}

export interface OriginCheckResult {
  allowed: boolean
  /** `same-host`, `configured`, `no-origin-header` or `unexpected-origin`. */
  reason: string
}

export function isStateChangingMethod(method: string) {
  return ['POST', 'PUT', 'PATCH', 'DELETE'].includes((method || '').toUpperCase())
}

function hostOf(value: string | null | undefined): string | null {
  if (!value) return null
  try {
    return new URL(value).host.toLowerCase()
  } catch {
    return null
  }
}

function normaliseHost(value: string | null | undefined): string | null {
  if (!value) return null
  const trimmed = value.trim().toLowerCase().replace(/\/$/, '')
  if (!trimmed) return null
  // A bare host header (or a value that fails URL parsing) is already a host.
  return hostOf(trimmed) ?? (trimmed.split('/')[0] || null)
}

export function checkRequestOrigin(input: OriginCheckInput): OriginCheckResult {
  const declared = hostOf(input.origin) ? input.origin!.trim() : null
  const declaredHost = hostOf(declared) ?? hostOf(input.referer)
  if (!declaredHost) return { allowed: true, reason: 'no-origin-header' }

  const ownHost = normaliseHost(input.forwardedHost) ?? normaliseHost(input.host)
  if (ownHost && declaredHost === ownHost) return { allowed: true, reason: 'same-host' }

  const configured = (input.allowedOrigins ?? [])
    .flatMap(entry => entry.split(','))
    .map(entry => normaliseHost(entry))
    .filter((entry): entry is string => Boolean(entry))
  if (configured.includes(declaredHost)) return { allowed: true, reason: 'configured' }

  return { allowed: false, reason: 'unexpected-origin' }
}
