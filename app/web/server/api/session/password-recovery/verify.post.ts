import { apiUrl, upstreamError } from '../../../utils/hrms'

export default defineEventHandler(async (event) => {
  const payload = await readBody<{ recovery_token?: string, code?: string }>(event)
  if (!payload.recovery_token || !payload.code?.trim()) throw createError({ statusCode: 400, statusMessage: 'Enter the authenticator code.' })
  try {
    return await $fetch(apiUrl(event, 'auth/password-recovery/verify'), {
      method: 'POST',
      body: { recovery_token: payload.recovery_token, code: payload.code.trim() }
    })
  } catch (error) { throw upstreamError(error, event) }
})
