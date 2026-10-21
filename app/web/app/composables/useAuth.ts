/**
 * composable for shared authentication state.
 *
 * State lives in `useState` so it is shared across all components (and
 * SSR-safe). The user is fetched once per request via the session endpoint
 * (`/api/session/me`) and cached until `force` refresh or logout.
 */
import type { AccessScope, BusinessRole, CurrentUser, LoginPayload, LoginResult, MfaEnrollment } from '#shared/types/auth'
import { appendResponseHeader, type H3Event } from 'h3'

function forwardSessionCookies(event?: H3Event, headers?: Headers) {
  if (!event || !headers) return
  for (const cookie of headers.getSetCookie()) appendResponseHeader(event, 'set-cookie', cookie)
}

export function useAuth() {
  const requestFetch = useRequestFetch()
  const user = useState<CurrentUser | null>('auth-user', () => null)
  const initialized = useState('auth-initialized', () => false)
  const loading = useState('auth-loading', () => false)

  /** "First Last" for display, falling back to username, then empty. */
  const displayName = computed(() => user.value
    ? [user.value.first_name, user.value.last_name].filter(Boolean).join(' ') || user.value.username
    : '')
  /** Up to two uppercase initials for the avatar circle. */
  const initials = computed(() => displayName.value.split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase())
  /** Super Admin bypasses permission checks; everyone else checks their list. */
  const hasPermission = (permission: string) => Boolean(user.value?.is_superuser || user.value?.permissions?.includes(permission))
  /**
   * Elevated business role, if any — for genuinely role-specific experiences
   * (the Organization Owner dashboard). Action and nav visibility should gate
   * on `hasPermission` instead: the server enforces permission *and* scope on
   * every endpoint, so a hidden control is convenience, never security.
   */
  const businessRole = computed<BusinessRole | null>(() => user.value?.business_role ?? null)
  /** Where the business role applies; `SELF` for a plain employee. */
  const scopeType = computed<AccessScope>(() => user.value?.scope_type ?? 'SELF')

  /**
   * Load the signed-in user from the cookie-backed session.
   * Cached: subsequent calls return immediately unless `force` is set
   * (used after login/logout or a manual profile refresh).
   */
  async function fetchUser(force = false) {
    if (initialized.value && !force) return user.value
    let resolved = false
    const event = import.meta.server ? useRequestEvent() : undefined
    const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined
    try {
      const response = await $fetch.raw<CurrentUser>('/api/session/me', {
        headers
      })
      forwardSessionCookies(event, response.headers)
      user.value = response._data ?? null
      resolved = true
    } catch (error) {
      forwardSessionCookies(event, (error as { response?: { headers?: Headers } }).response?.headers)
      const status = (error as { statusCode?: number, status?: number }).statusCode
        ?? (error as { statusCode?: number, status?: number }).status
      if (status !== 401) throw error
      user.value = null
      resolved = true
    } finally {
      // A transient API error must not be cached as a signed-out session.
      if (resolved) initialized.value = true
    }
    return user.value
  }

  /**
   * Sign in. Returns the signed-in user, or a second-factor challenge that the
   * caller must complete with `completeMfa` before the session exists.
   */
  async function login(payload: LoginPayload): Promise<LoginResult> {
    loading.value = true
    try {
      const result = await requestFetch<LoginResult>('/api/session/login', { method: 'POST', body: payload })
      if ('mfa_required' in result) return result
      user.value = result
      initialized.value = true
      return result
    } finally {
      loading.value = false
    }
  }

  /** Finish a second-factor challenge (or confirm first-time enrolment). */
  async function completeMfa(credential: { mfa_token: string, code: string, enrollment?: boolean }) {
    loading.value = true
    try {
      user.value = await requestFetch<CurrentUser>('/api/session/mfa', { method: 'POST', body: credential })
      initialized.value = true
      return user.value
    } finally {
      loading.value = false
    }
  }

  /** Reveal a new authenticator secret for a login challenge (shown once). */
  async function startMfaEnrollment(mfaToken: string) {
    return await requestFetch<MfaEnrollment>('/api/session/mfa/enroll', { method: 'POST', body: { mfa_token: mfaToken } })
  }

  /** True while the account is still on a temporary password set by HR/ERP. */
  const mustChangePassword = computed(() => Boolean(user.value?.must_change_password))

  /** Forget client-side state without calling the API (e.g. after a password change). */
  function clear() {
    user.value = null
    initialized.value = true
  }

  async function logout() {
    const destination = user.value?.is_superuser || user.value?.role === 'SUPER_ADMIN' ? '/admin/login' : '/login'
    try {
      await requestFetch('/api/session', { method: 'DELETE' })
    } catch {
      // A failed revocation request must not trap the user in a signed-in UI:
      // clear the client state regardless and let the server-side cookie
      // expire. (The API also revokes on password change, so this is recovery,
      // not the primary revocation path.)
    }
    user.value = null
    initialized.value = true
    await navigateTo(destination)
  }

  return {
    user,
    initialized,
    loading,
    displayName,
    initials,
    hasPermission,
    businessRole,
    scopeType,
    mustChangePassword,
    fetchUser,
    login,
    completeMfa,
    startMfaEnrollment,
    logout,
    clear
  }
}
