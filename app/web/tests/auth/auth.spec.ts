import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function open(page: Page, path = '/login') {
  await page.route('**/api/session/me', route => route.fulfill({ status: 401, json: { message: 'Signed out' } }))
  await page.goto(path)
  await expect(page.locator('.auth-shell')).toBeVisible()
  await expect(page.locator('.auth-theme-toggle')).toBeVisible()
  await page.waitForFunction(() => (document.querySelector('#__nuxt') as Element & { __vue_app__?: { config: { globalProperties: { $nuxt?: { isHydrating: boolean } } } } })?.__vue_app__?.config.globalProperties.$nuxt?.isHydrating === false)
}

async function credentials(page: Page) {
  await page.getByLabel(/Mobile number or username|Technical username/).fill('test-user')
  await page.getByLabel('Password', { exact: true }).fill('sample-password')
}

for (const colorScheme of ['light', 'dark'] as const) {
  for (const width of [360, 390, 768, 1366, 1920]) {
    test(`responsive ${width} ${colorScheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' })
      await page.setViewportSize({ width, height: 900 })
      for (const path of ['/login', '/admin/login', '/forgot-password']) {
        const errors: string[] = []
        page.on('pageerror', error => errors.push(error.message))
        page.on('console', (message) => {
          if (/hydration/i.test(message.text())) errors.push(message.text())
        })
        await open(page, path)
        await expect(page.locator('html')).toHaveClass(colorScheme === 'dark' ? /dark/ : /light/)
        await expect(page.getByRole('contentinfo')).toContainText('Datlabs. All rights reserved.')
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        await expect(page.locator('.auth-story')).toBeVisible({ visible: path !== '/admin/login' && width >= 1024 })
        expect(errors).toEqual([])
        if (width === 390 || width === 1366) {
          await page.screenshot({ path: `test-results/auth/${path.replaceAll('/', '-')}-${width}-${colorScheme}.png`, fullPage: true })
        }
      }
    })
  }
}

test('both account types: visibility, pending, error and correct payload', async ({ page }) => {
  for (const [path, accountType] of [['/login', 'employee'], ['/admin/login', 'super_admin']]) {
    await open(page, path)
    await credentials(page)
    await page.getByRole('button', { name: 'Show password' }).click()
    await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'text')
    await page.getByRole('button', { name: 'Hide password' }).click()
    let requests = 0
    await page.route('**/api/session/login', async (route) => {
      requests++
      expect(route.request().postDataJSON().accountType).toBe(accountType)
      await new Promise(resolve => setTimeout(resolve, 300))
      await route.fulfill({ status: 429, headers: { 'Retry-After': '30' }, json: { statusMessage: 'Try again in 30 seconds.' } })
    })
    await page.getByRole('button', { name: /^Sign in/ }).click()
    await expect(page.getByRole('button', { name: /^Sign in/ })).toBeDisabled()
    await page.getByLabel('Password', { exact: true }).press('Enter')
    await expect(page.getByRole('alert')).toContainText('Try again in 30 seconds.')
    expect(requests).toBe(1)
    await page.unroute('**/api/session/login')
  }
})

test('empty credentials, notice and switching entry points', async ({ page }) => {
  await open(page, '/login?notice=password-changed')
  await expect(page.getByRole('status')).toContainText('Your password was changed')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Enter your mobile number or username')
  await page.getByRole('link', { name: /Technical administrator/ }).click()
  await expect(page).toHaveURL(/admin\/login/)
  await page.getByRole('link', { name: 'Employee sign-in', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('MFA supports recovery codes, errors and cancellation', async ({ page }) => {
  await page.route('**/api/session/login', route => route.fulfill({ json: { mfa_required: true, mfa_token: 'mock-token', enrollment_required: false, expires_in: 300 } }))
  await page.route('**/api/session/mfa', async (route) => {
    expect(route.request().postDataJSON().code).toBe('ABCD-EFGH')
    await route.fulfill({ status: 401, json: { statusMessage: 'That code was not accepted.' } })
  })
  await open(page)
  await credentials(page)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByLabel('Authenticator or recovery code').fill('ABCD-EFGH')
  await expect(page.getByLabel('Authenticator or recovery code')).not.toHaveAttribute('inputmode', 'numeric')
  await page.getByRole('button', { name: 'Verify and sign in' }).click()
  await expect(page.getByRole('alert')).toContainText('That code was not accepted.')
  await page.getByRole('button', { name: 'Back to sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to People' })).toBeVisible()
})

test('MFA enrollment remains readable on small screens', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 640 })
  await page.route('**/api/session/login', route => route.fulfill({ json: { mfa_required: true, mfa_token: 'mock-token', enrollment_required: true, expires_in: 300 } }))
  await page.route('**/api/session/mfa/enroll', route => route.fulfill({ json: { secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://totp/People:test?secret=JBSWY3DPEHPK3PXP&issuer=People', recovery_codes: ['ABCD-EFGH', 'IJKL-MNOP'] } }))
  await open(page, '/admin/login')
  await credentials(page)
  await page.getByRole('button', { name: 'Sign in to administration' }).click()
  await expect(page.getByRole('img', { name: /QR code/ })).toBeVisible()
  await page.getByRole('button', { name: /Can’t scan/ }).click()
  await expect(page.getByText('JBSW Y3DP EHPK 3PXP')).toBeVisible()
  await expect(page.getByText('ABCD-EFGH', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('recovery: keyboard submission, mismatch, completion and expiry', async ({ page }) => {
  await page.route('**/api/session/password-recovery/start', route => route.fulfill({ json: { recovery_token: 'mock-recovery' } }))
  await page.route('**/api/session/password-recovery/verify', route => route.fulfill({ json: { recovery_token: 'mock-reset' } }))
  await page.route('**/api/session/password-recovery/reset', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ reset_token: 'mock-reset', new_password: 'New-example-password' })
    await route.fulfill({ json: { message: 'Complete' } })
  })
  await open(page, '/forgot-password')
  await page.getByLabel('Mobile number or username').fill('test-user')
  await page.getByLabel('Mobile number or username').press('Enter')
  await page.getByLabel('Authenticator code').fill('123456')
  await page.getByLabel('Authenticator code').press('Enter')
  await page.getByLabel('New password', { exact: true }).fill('New-example-password')
  await page.getByLabel('Confirm new password').fill('mismatch')
  await page.getByRole('button', { name: 'Set new password' }).click()
  await expect(page.getByRole('alert')).toContainText('The passwords do not match')
  await page.getByLabel('Confirm new password').fill('New-example-password')
  await page.getByRole('button', { name: 'Set new password' }).click()
  await expect(page.getByRole('status')).toContainText('Password changed')
  await open(page, '/forgot-password')
  await page.unroute('**/api/session/password-recovery/verify')
  await page.route('**/api/session/password-recovery/verify', route => route.fulfill({ status: 401, json: { statusMessage: 'Recovery session expired' } }))
  await page.getByLabel('Mobile number or username').fill('test-user')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByLabel('Authenticator code').fill('123456')
  await page.getByRole('button', { name: 'Verify authenticator' }).click()
  await expect(page.getByLabel('Mobile number or username')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Your recovery session expired')
})

test('theme persists and enlarged text reflows', async ({ page }) => {
  for (const path of ['/admin/login', '/login']) {
    await open(page, path)
    const wasDark = await page.locator('html').evaluate(el => el.classList.contains('dark'))
    const nextTheme = wasDark ? 'light' : 'dark'
    await page.locator('.auth-theme-toggle').click()
    await expect(page.locator('html')).toHaveClass(new RegExp(nextTheme))
    await page.reload()
    await page.waitForFunction(() => (document.querySelector('#__nuxt') as Element & { __vue_app__?: { config: { globalProperties: { $nuxt?: { isHydrating: boolean } } } } })?.__vue_app__?.config.globalProperties.$nuxt?.isHydrating === false)
    await expect(page.locator('html')).toHaveClass(new RegExp(nextTheme))
    await expect(page.getByRole('button', { name: wasDark ? 'Switch to dark mode' : 'Switch to light mode' })).toBeEnabled()
  }
  await page.setViewportSize({ width: 360, height: 640 })
  await page.addStyleTag({ content: 'html { font-size: 200%; }' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByLabel('Mobile number or username').focus()
  expect(await page.getByLabel('Mobile number or username').evaluate(el => getComputedStyle(el).outlineStyle !== 'none' || getComputedStyle(el).boxShadow !== 'none')).toBe(true)
})

const signedInUser = {
  id: 1, email: 'test@example.invalid', username: 'test-user', is_active: true,
  is_superuser: false, is_verified: true, must_change_password: false,
  role: 'EMPLOYEE', business_role: null, scope_type: 'SELF', permissions: ['attendance.view_self']
}

test('successful sign-in and MFA preserve redirect and forced password change', async ({ page }) => {
  await page.route('**/api/hrms/**', route => route.fulfill({ status: 503, json: { message: 'Mock backend unavailable' } }))
  await page.route('**/api/session/login', route => route.fulfill({ json: signedInUser }))
  await open(page, '/login?redirect=/attendance')
  await credentials(page)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/attendance$/)
  await page.unroute('**/api/session/login')
  await page.route('**/api/session/login', route => route.fulfill({ json: { ...signedInUser, must_change_password: true } }))
  await open(page)
  await credentials(page)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/settings\?change-password=1$/)
  await page.unroute('**/api/session/login')
  await page.route('**/api/session/login', route => route.fulfill({ json: { mfa_required: true, mfa_token: 'mock-token', enrollment_required: false, expires_in: 300 } }))
  await page.route('**/api/session/mfa', route => route.fulfill({ json: { ...signedInUser, must_change_password: true } }))
  await open(page)
  await credentials(page)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByLabel('Authenticator or recovery code').fill('123456')
  await page.getByRole('button', { name: 'Verify and sign in' }).click()
  await expect(page).toHaveURL(/\/settings\?change-password=1$/)
})
