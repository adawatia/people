import { apiUrl, upstreamError } from '../../../utils/hrms'

export default defineEventHandler(async (event) => {
  const payload = await readBody<{ identity?: string }>(event)
  if (!payload.identity?.trim()) throw createError({ statusCode: 400, statusMessage: 'Enter your mobile number or username.' })
  try {
    return await $fetch(apiUrl(event, 'auth/password-recovery/start'), {
      method: 'POST',
      body: { identity: payload.identity.trim() }
    })
  } catch (error) { throw upstreamError(error, event) }
})
