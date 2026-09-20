import { apiUrl, REFRESH_COOKIE, SESSION_COOKIE, upstreamError } from '../../utils/hrms'

export default defineEventHandler(async (event) => {
  const refresh = getCookie(event, REFRESH_COOKIE)
  if (refresh) {
    try {
      await $fetch(apiUrl(event, 'auth/session'), { method: 'DELETE', body: { refresh_token: refresh } })
    } catch (error) {
      console.warn(upstreamError(error))
    }
  }
  deleteCookie(event, SESSION_COOKIE, { path: '/' })
  deleteCookie(event, REFRESH_COOKIE, { path: '/' })
  setResponseStatus(event, 204)
  return null
})
