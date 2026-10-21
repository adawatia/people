import type { CurrentUser } from '#shared/types/auth'

export function useHrmsApi() {
  const requestFetch = useRequestFetch()
  async function request<T>(path: string, options: Parameters<typeof $fetch<T>>[1] = {}) {
    try {
      return await requestFetch<T>(`/api/hrms/${path.replace(/^\//, '')}`, options as never)
    } catch (error) {
      const status = (error as { statusCode?: number, status?: number }).statusCode || (error as { status?: number }).status
      if (status === 401) {
        const userState = useState<CurrentUser | null>('auth-user', () => null)
        const isSuperAdmin = Boolean(userState.value?.is_superuser || userState.value?.role === 'SUPER_ADMIN')
        userState.value = null
        const loginPath = isSuperAdmin ? '/admin/login' : '/login'
        await navigateTo(`${loginPath}?redirect=${encodeURIComponent(useRoute().fullPath)}`)
      }
      throw error
    }
  }
  return { request }
}
