import { apiUrl, upstreamError } from '../../../../utils/hrms'

export default defineEventHandler(async (event) => {
  const payload = await readBody<{ reset_token?: string, new_password?: string }>(event)
  if (!payload.reset_token || !payload.new_password) throw createError({ statusCode: 400, statusMessage: 'Enter a new password.' })
  try {
    return await $fetch(apiUrl(event, 'auth/password-recovery/reset'), {
      method: 'POST',
      body: { reset_token: payload.reset_token, new_password: payload.new_password }
    })
  } catch (error) { throw upstreamError(error) }
})
