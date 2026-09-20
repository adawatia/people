import type { CurrentUser, LoginPayload } from '#shared/types/auth'

export function useAuth() {
  const requestFetch = useRequestFetch()
  const user = useState<CurrentUser | null>('auth-user', () => null)
  const initialized = useState('auth-initialized', () => false)
  const loading = useState('auth-loading', () => false)
  const displayName = computed(() => user.value
    ? [user.value.first_name, user.value.last_name].filter(Boolean).join(' ') || user.value.username
    : '')
  const initials = computed(() => displayName.value.split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase())
  const hasPermission = (permission: string) => Boolean(user.value?.is_superuser || user.value?.permissions?.includes(permission))
  const hasRole = (role: CurrentUser['role']) => Boolean(user.value?.is_superuser || user.value?.role === role)

  async function fetchUser(force = false) {
    if (initialized.value && !force) return user.value
    try {
      user.value = await requestFetch<CurrentUser>('/api/session/me')
    } catch {
      user.value = null
    } finally {
      initialized.value = true
    }
    return user.value
  }

  async function login(payload: LoginPayload) {
    loading.value = true
    try {
      user.value = await requestFetch<CurrentUser>('/api/session/login', { method: 'POST', body: payload })
      initialized.value = true
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    await requestFetch('/api/session', { method: 'DELETE' })
    user.value = null
    initialized.value = true
    await navigateTo('/login')
  }

  return { user, initialized, loading, displayName, initials, hasPermission, hasRole, fetchUser, login, logout }
}
