import { SESSION_COOKIE } from '../../utils/hrms'

export default defineEventHandler((event) => {
  deleteCookie(event, SESSION_COOKIE, { path: '/' })
  setResponseStatus(event, 204)
  return null
})
