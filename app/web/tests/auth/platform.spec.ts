import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const previewUser = {
  id: 901, email: 'preview@example.invalid', username: 'preview', first_name: 'Preview', last_name: 'Account',
  is_active: true, is_superuser: false, is_verified: true, must_change_password: false,
  role: 'HR_ADMIN', business_role: 'HR_ADMIN', scope_type: 'UNIT',
  permissions: ['employee.view', 'attendance.view', 'attendance.view_self', 'leave.apply', 'leave.manage', 'leave.approve', 'attendance.process', 'shift.assign', 'reports.view', 'designation.view']
}

async function openPlatform(page: Page, technical = false, userOverrides: Partial<typeof previewUser> = {}) {
  const user = technical ? { ...previewUser, is_superuser: true, role: 'SUPER_ADMIN', business_role: null, permissions: [] } : { ...previewUser, ...userOverrides }
  await page.route('**/api/session/me', route => route.fulfill({ status: 401, json: { message: 'Signed out' } }))
  await page.route('**/api/session/login', route => route.fulfill({ json: user }))
  await page.route('**/api/hrms/**', route => route.fulfill({ status: 503, json: { message: 'Preview data unavailable' } }))
  await page.route('**/api/hrms/notifications*', route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20, unread_count: 0 } }))
  await page.goto('/login?redirect=/notifications')
  await page.waitForFunction(() => (document.querySelector('#__nuxt') as Element & { __vue_app__?: { config: { globalProperties: { $nuxt?: { isHydrating: boolean } } } } })?.__vue_app__?.config.globalProperties.$nuxt?.isHydrating === false)
  await page.getByLabel('Mobile number or username').fill('preview')
  await page.getByLabel('Password', { exact: true }).fill('synthetic-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Search pages', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Notifications', exact: true }).last()).toBeVisible()
  await expect(page.locator('.nuxt-loading-indicator')).toHaveCSS('opacity', '0')
}

for (const colorScheme of ['light', 'dark'] as const) {
  for (const width of [360, 390, 768, 1366, 1920]) {
    test(`platform responsive ${width} ${colorScheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' })
      await page.setViewportSize({ width, height: 900 })
      const hydrationErrors: string[] = []
      page.on('console', (message) => {
        if (/hydration/i.test(message.text())) hydrationErrors.push(message.text())
      })
      page.on('pageerror', error => hydrationErrors.push(error.message))
      await openPlatform(page)
      await expect(page.locator('.platform-sidebar')).toBeVisible({ visible: width >= 1024 })
      await expect(page.getByRole('navigation', { name: 'Mobile navigation' })).toBeVisible({ visible: width < 1024 })
      await expect(page.locator('.platform-header h1, .platform-page-context, .platform-workspace-description')).toHaveCount(0)
      await expect(page.locator('.platform-sidebar .platform-profile')).toHaveCount(0)
      await expect(page.locator('.platform-sidebar')).not.toContainText('by Datlabs')
      await expect(page.locator('.platform-header').getByRole('link', { name: 'Profile: Preview Account' })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      expect(hydrationErrors).toEqual([])
      if (width >= 1024) {
        await page.getByLabel('Workspace', { exact: true }).selectOption('HR')
        await expect(page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Employees', exact: true })).toBeVisible()
      }
      if (width === 390 || width === 1366) {
        await page.addStyleTag({ content: '#nuxt-devtools-container { display: none !important; }' })
        if (width >= 1024) {
          for (const icon of await page.locator('.platform-sidebar .platform-nav-link > span:first-child').all()) {
            await expect.poll(() => icon.evaluate(el => getComputedStyle(el).maskImage)).not.toBe('none')
          }
        }
        await page.screenshot({ path: `test-results/auth/platform-${width}-${colorScheme}.png`, fullPage: false })
      }
    })
  }
}

test('platform navigation, keyboard search, mobile workspace and logout', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 900 })
  await openPlatform(page)
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('dialog', { name: 'Search Emploi' })).toBeVisible()
  await page.getByPlaceholder('Search pages', { exact: true }).fill('Security')
  await page.getByPlaceholder('Search pages', { exact: true }).fill('Settings')
  await page.getByRole('dialog').getByRole('button', { name: 'Settings', exact: true }).click()
  await expect(page).toHaveURL(/settings/)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: /Workspace: My Workspace/ }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'HR Workspace' }).click()
  await expect(page).toHaveURL(/workspace=HR/)
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await page.getByRole('button', { name: 'More navigation' }).click()
  await expect(page.getByRole('dialog').getByRole('link', { name: 'Leave management' })).toBeVisible()
  await page.addStyleTag({ content: '#nuxt-devtools-container { display: none !important; }' })
  await expect.poll(async () => {
    const box = await page.getByRole('dialog').getByRole('button', { name: 'Sign out', exact: true }).boundingBox()
    return Boolean(box && box.y >= 0 && box.y + box.height <= 844)
  }).toBe(true)
  await page.screenshot({ path: 'test-results/auth/platform-mobile-menu.png', fullPage: false })
  await page.route('**/api/session', route => route.fulfill({ json: { ok: true } }))
  await page.getByRole('dialog').getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/login/)
})

test('technical sidebar excludes workforce links', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 900 })
  await openPlatform(page, true)
  const nav = page.getByRole('navigation', { name: 'Primary navigation' })
  await expect(nav.getByRole('link', { name: 'System administration' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Employees' })).toHaveCount(0)
  await expect(nav.getByRole('link', { name: 'Leave' })).toHaveCount(0)
})

test('sidebar collapse persists, workspaces remain accessible and sign-out handles failure', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 900 })
  await openPlatform(page)
  await page.locator('.platform-header').getByRole('button', { name: 'Collapse sidebar' }).click()
  await expect(page.getByRole('button', { name: 'Expand sidebar' })).toHaveAttribute('aria-expanded', 'false')
  expect(await page.locator('.platform-sidebar').evaluate(el => el.getBoundingClientRect().width)).toBe(76)
  await expect(page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Attendance', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Switch workspace: My Workspace' }).click()
  await page.getByRole('menuitem', { name: 'HR Workspace' }).click()
  await expect(page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Employees', exact: true })).toBeVisible()
  expect((await page.context().cookies()).find(cookie => cookie.name === 'people_sidebar_collapsed')?.value).toBe('true')
  await page.addStyleTag({ content: '#nuxt-devtools-container { display: none !important; }' })
  await expect(page.getByRole('button', { name: 'Search pages', exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/auth/platform-collapsed.png', fullPage: false })
  await openPlatform(page)
  await expect(page.getByRole('button', { name: 'Expand sidebar' })).toBeVisible()
  await page.getByRole('button', { name: 'Expand sidebar' }).click()
  expect(await page.locator('.platform-sidebar').evaluate(el => el.getBoundingClientRect().width)).toBe(256)
  await page.route('**/api/session', async (route) => {
    await new Promise(resolve => setTimeout(resolve, 250))
    await route.fulfill({ status: 503, json: { message: 'Test unavailable' } })
  })
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeDisabled()
  await expect(page.getByText('Could not sign out', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeEnabled()
  await page.unroute('**/api/session')
  await page.route('**/api/session', route => route.fulfill({ json: { ok: true } }))
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page).toHaveURL(/login/)
})

test('controls-only header truncates long profile names and links to profile', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 900 })
  const firstName = 'Alexandria-Catherine'
  const lastName = 'Montgomery-Wellington'
  await openPlatform(page, false, { first_name: firstName, last_name: lastName })
  const profile = page.locator('.platform-header').getByRole('link', { name: `Profile: ${firstName} ${lastName}` })
  await expect(profile).toBeVisible()
  expect(await page.locator('.platform-profile-name').evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
  await profile.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/profile/)
  await page.setViewportSize({ width: 360, height: 900 })
  await expect(profile).toBeVisible()
  await expect(page.locator('.platform-profile-copy')).not.toBeVisible()
  await expect(page.getByRole('button', { name: 'Collapse sidebar' })).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('single-workspace sidebar omits redundant workspace section and signout is bordered', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 900 })
  await openPlatform(page, false, { permissions: [], role: 'EMPLOYEE', business_role: 'EMPLOYEE' })
  await expect(page.locator('.platform-sidebar .platform-workspace')).toHaveCount(0)
  await expect(page.locator('.platform-sidebar')).not.toContainText('My Workspace')
  const signOut = page.locator('.platform-sign-out')
  expect(await signOut.evaluate(el => getComputedStyle(el).borderTopWidth)).toBe('1px')
  expect(await signOut.evaluate(el => getComputedStyle(el).color === getComputedStyle(el).borderTopColor)).toBe(true)
  await page.keyboard.press('Tab')
  await signOut.focus()
  expect(await signOut.evaluate(el => el.matches(':focus-visible'))).toBe(true)
  await page.getByRole('button', { name: 'Collapse sidebar' }).click()
  await expect(page.getByRole('button', { name: /Switch workspace:/ })).toHaveCount(0)
  await expect(signOut).toBeVisible()
})
