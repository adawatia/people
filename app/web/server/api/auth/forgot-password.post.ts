import { apiUrl, upstreamError } from '../../utils/hrms'

export default defineEventHandler(async (event) => {
  const payload = await readBody<{ email?: string }>(event)
  if (!payload.email?.trim()) throw createError({ statusCode: 400, statusMessage: 'Enter your work email.' })
  try {
    await $fetch(apiUrl(event, 'auth/forgot-password'), {
      method: 'POST',
      body: { email: payload.email.trim() }
    })
    return { message: 'If an account matches that email, a reset link is on its way.' }
  } catch (error) {
    throw upstreamError(error)
  }
})
