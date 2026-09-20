import { apiUrl, authHeaders, SESSION_COOKIE, upstreamError } from '../../utils/hrms'

export default defineEventHandler(async (event) => {
  const path = getRouterParam(event, 'path') || ''
  const method = getMethod(event)
  const query = getQuery(event)
  const body = ['GET', 'HEAD'].includes(method) ? undefined : await readBody(event)

  try {
    return await $fetch(apiUrl(event, path), {
      method: method as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
      query,
      body,
      headers: authHeaders(event)
    })
  } catch (error) {
    const status = (error as { statusCode?: number, status?: number }).statusCode || (error as { status?: number }).status
    if (status === 401) deleteCookie(event, SESSION_COOKIE, { path: '/' })
    throw upstreamError(error)
  }
})
