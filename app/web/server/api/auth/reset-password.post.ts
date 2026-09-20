import { apiUrl, upstreamError } from '../../utils/hrms'

export default defineEventHandler(async (event) => {
  const payload = await readBody<{ token?: string, password?: string }>(event)
  if (!payload.token || !payload.password) throw createError({ statusCode: 400, statusMessage: 'The reset link or password is missing.' })
  try {
    await $fetch(apiUrl(event, 'auth/reset-password'), { method: 'POST', body: payload })
    return { message: 'Your password has been updated.' }
  } catch (error) {
    throw upstreamError(error)
  }
})
