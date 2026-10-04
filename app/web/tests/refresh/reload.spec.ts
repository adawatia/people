import { createServer } from 'node:http'
import { expect, test } from '@playwright/test'

const user = {
  id: 1, email: 'reload@example.invalid', username: 'reload', first_name: 'Reload', last_name: 'Tester',
  is_active: true, is_superuser: false, is_verified: true, must_change_password: false,
  role: 'EMPLOYEE', business_role: 'EMPLOYEE', scope_type: 'SELF', permissions: ['attendance.view_self']
}

let rotations = 0
let upstreamUnavailable = true
const api = createServer(async (request, response) => {
  const send = (status: number, body: unknown) => {
    response.writeHead(status, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify(body))
  }
  if (request.url === '/api/v1/auth/session/refresh') {
    let body = ''
    for await (const part of request) body += part.toString()
    if (JSON.parse(body).refresh_token !== 'refresh-start' || rotations > 0) return send(401, { detail: 'Refresh token reuse detected' })
    rotations++
    return send(200, { access_token: 'fresh-access', refresh_token: 'refresh-next', expires_in: 900, absolute_expires_at: new Date(Date.now() + 3600000).toISOString() })
  }
  if (request.url === '/api/v1/users/me') {
    if (request.headers.authorization === 'Bearer offline-access') {
      return upstreamUnavailable ? send(503, { detail: 'Service unavailable' }) : send(200, user)
    }
    return request.headers.authorization === 'Bearer fresh-access'
      ? send(200, user)
      : send(401, { detail: 'Invalid access token' })
  }
  if (request.url?.startsWith('/api/v1/notifications')) return send(200, { items: [], total: 0, page: 1, page_size: 20, unread_count: 0 })
  return send(404, { detail: 'Not found' })
})

test.beforeAll(async () => {
  await new Promise<void>(resolve => api.listen(3901, '127.0.0.1', resolve))
})

test.afterAll(async () => {
  await new Promise<void>((resolve, reject) => api.close(error => error ? reject(error) : resolve()))
})

test('missing access cookie refreshes once and repeated full reloads stay rendered', async ({ page, context }) => {
  await context.addCookies([{ name: 'people_refresh', value: 'refresh-start', url: 'http://127.0.0.1:3101', httpOnly: true, sameSite: 'Lax' }])
  await page.goto('/notifications')
  await expect(page.getByRole('heading', { name: 'Notifications', exact: true }).last()).toBeVisible()
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Notifications', exact: true }).last()).toBeVisible()
    await expect(page.locator('body')).not.toBeEmpty()
  }
  expect(rotations).toBe(1)
  const cookies = await context.cookies()
  expect(cookies.find(cookie => cookie.name === 'people_refresh')?.value).toBe('refresh-next')
})

test('temporary API failure shows recovery UI and preserves session', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await context.addCookies([{ name: 'people_session', value: 'offline-access', url: 'http://127.0.0.1:3101', httpOnly: true, sameSite: 'Lax' }])
  await page.goto('/notifications')
  await expect(page.getByRole('heading', { name: 'This page is temporarily unavailable' })).toBeVisible()
  expect((await context.cookies()).find(cookie => cookie.name === 'people_session')?.value).toBe('offline-access')
  upstreamUnavailable = false
  // Nuxt's development-only error overlay sits above the production recovery UI.
  await page.addStyleTag({ content: 'nuxt-error-overlay { pointer-events: none !important; }' })
  await page.getByRole('link', { name: 'Try again' }).click()
  await expect(page.getByRole('heading', { name: 'Notifications', exact: true }).last()).toBeVisible()
})
