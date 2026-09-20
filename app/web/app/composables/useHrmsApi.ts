export function useHrmsApi() {
  const requestFetch = useRequestFetch()
  async function request<T>(path: string, options: Parameters<typeof $fetch<T>>[1] = {}) {
    try {
      return await requestFetch<T>(`/api/hrms/${path.replace(/^\//, '')}`, options)
    } catch (error) {
      const status = (error as { statusCode?: number, status?: number }).statusCode || (error as { status?: number }).status
      if (status === 401) {
        useState('auth-user', () => null).value = null
        await navigateTo(`/login?redirect=${encodeURIComponent(useRoute().fullPath)}`)
      }
      throw error
    }
  }
  return { request }
}
