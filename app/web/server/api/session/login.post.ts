import type { CurrentUser, LoginPayload } from '#shared/types/auth'
import { apiUrl, REFRESH_COOKIE, SESSION_COOKIE, upstreamError } from '../../utils/hrms'

export default defineEventHandler(async (event) => {
  const payload = await readBody<LoginPayload>(event)
  if (!payload.identity?.trim() || !payload.password) {
    throw createError({ statusCode: 400, statusMessage: 'Enter your email, username or mobile number and password.' })
  }

  try {
    const form = new URLSearchParams({ username: payload.identity.trim(), password: payload.password })
    const auth = await $fetch<{ access_token: string, token_type: string }>(apiUrl(event, 'auth/jwt/login'), {
      method: 'POST',
      body: form,
      headers: { 'content-type': 'application/x-www-form-urlencoded' }
    })
    setCookie(event, SESSION_COOKIE, auth.access_token, {
      httpOnly: true,
      secure: !import.meta.dev,
      sameSite: 'lax',
      path: '/',
      maxAge: 60 * 60 * 8
    })
    const session = await $fetch<{ access_token: string, refresh_token: string }>(apiUrl(event, 'auth/session'), {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.access_token}` }
    })
    setCookie(event, SESSION_COOKIE, session.access_token, { httpOnly: true, secure: !import.meta.dev, sameSite: 'lax', path: '/', maxAge: 60 * 15 })
    setCookie(event, REFRESH_COOKIE, session.refresh_token, { httpOnly: true, secure: !import.meta.dev, sameSite: 'lax', path: '/', maxAge: 60 * 60 * 24 * 30 })
    return await $fetch<CurrentUser>(apiUrl(event, 'users/me'), {
      headers: { Authorization: `Bearer ${session.access_token}` }
    })
  } catch (error) {
    throw upstreamError(error)
  }
})
