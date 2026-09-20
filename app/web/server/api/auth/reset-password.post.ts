import { apiUrl, REFRESH_COOKIE, SESSION_COOKIE, upstreamError } from '../../utils/hrms'

export default defineEventHandler(async (event) => {
  const payload = await readBody<{ token?: string, password?: string }>(event)
  if (!payload.token || !payload.password) throw createError({ statusCode: 400, statusMessage: 'The reset link or password is missing.' })
  try {
    await $fetch(apiUrl(event, 'auth/reset-password'), { method: 'POST', body: payload })
    const refresh = getCookie(event, REFRESH_COOKIE)
    if (refresh) await $fetch(apiUrl(event, 'auth/session'), { method: 'DELETE', body: { refresh_token: refresh } }).catch(() => undefined)
    deleteCookie(event, SESSION_COOKIE, { path: '/' })
    deleteCookie(event, REFRESH_COOKIE, { path: '/' })
    return { message: 'Your password has been updated.' }
  } catch (error) {
    throw upstreamError(error)
  }
})
