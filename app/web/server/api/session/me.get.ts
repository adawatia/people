import type { CurrentUser } from '#shared/types/auth'
import { apiUrl, authHeaders, SESSION_COOKIE, upstreamError } from '../../utils/hrms'

export default defineEventHandler(async (event) => {
  try {
    return await $fetch<CurrentUser>(apiUrl(event, 'users/me'), { headers: authHeaders(event) })
  } catch (error) {
    const status = (error as { statusCode?: number, status?: number }).statusCode || (error as { status?: number }).status
    if (status === 401) deleteCookie(event, SESSION_COOKIE, { path: '/' })
    throw upstreamError(error)
  }
})
