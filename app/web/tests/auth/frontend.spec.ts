import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const day = new Date().toISOString().slice(0, 10)
const emp = { id: 901, employee_code: 'PREVIEW-901', first_name: 'Preview', last_name: 'Employee', full_name: 'Preview Employee', official_email: 'preview@example.invalid', employment_type: 'FULL_TIME', status: 'ACTIVE', department_id: 1, department_name: 'Preview department', unit_id: 1, unit_name: 'Preview unit', designation_name: 'Preview designation', date_of_joining: '2025-01-01', created_at: '2025-01-01T00:00:00Z' }
const permissions = ['employee.view', 'attendance.view', 'attendance.view_department', 'attendance.view_self', 'attendance.process', 'attendance.correct', 'leave.apply', 'leave.view_self', 'leave.approve', 'leave.reject', 'leave.manage', 'leave.cancel', 'work_arrangement.apply', 'work_arrangement.approve', 'work_arrangement.reject', 'work_arrangement.cancel', 'work_arrangement.manage', 'overtime.view_self', 'overtime.view_department', 'overtime.approve', 'shift.assign', 'shift.view_self', 'reports.view', 'reports.attendance', 'reports.leave', 'designation.view']
const user = { id: 901, employee_id: 901, username: 'preview', email: 'preview@example.invalid', first_name: 'Preview', last_name: 'Account', is_active: true, is_verified: true, is_superuser: false, must_change_password: false, role: 'HR_ADMIN', business_role: 'HR_ADMIN', scope_type: 'UNIT', permissions }
const metric = { employeeMetrics: { monthlyPresent: 18, monthlyAbsent: 1, monthlyLeave: 2, overtimeHours: 4, todayStatus: 'PRESENT', punchIn: '09:00', punchOut: null, currentShift: { name: 'Preview day shift', shiftDate: day, startsAt: `${day}T09:00:00+05:30`, endsAt: `${day}T18:00:00+05:30` }, upcomingShift: null, leaveBalances: [] }, unitMetrics: { totalHeadcount: 24, presentCount: 21, leaveCount: 2, pendingLeaves: 1, pendingCorrections: 0 }, pendingApprovals: [{ id: 1, employeeName: 'Preview Employee', detail: 'Annual leave · 2 days', type: 'LEAVE', timeAgo: 'Today' }] }
const org = { id: 1, name: 'Preview unit', headcount: 24, present: 21, absent: 1, on_leave: 2, exceptions: 1, attendance_rate: 87.5, approved_overtime_minutes: 240 }
const leave = { id: 1, employee_id: 901, employee_name: 'Preview Employee', employee_code: 'PREVIEW-901', leave_type_id: 1, leave_type_name: 'Annual leave', from_date: day, to_date: day, days_count: 1, half_day: false, reason: 'Synthetic preview request', status: 'PENDING', applied_at: `${day}T09:00:00Z` }
const paged = <T>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 25, total_pages: 1, has_next: false, has_prev: false })
const fixtures: Record<string, unknown> = {
  'dashboard/metrics': metric,
  'dashboard/technical-metrics': { users: 24, employees: 24, units: 2, departments: 4, designations: 6 },
  'reports/attendance-matrix': { ...paged([{ employee_id: 901, employee_code: 'PREVIEW-901', employee_name: 'Preview Employee', department_name: 'Preview department', day_status_map: { 1: 'P', 2: 'A' }, total_present: 18, total_absent: 1, total_leave: 2 }]), year: 2026, month: 10, total_days_in_month: 31 },
  'reports/leave-summary': { ...paged([{ employee_id: 901, employee_code: 'PREVIEW-901', employee_name: 'Preview Employee', leave_type_name: 'Annual leave', leave_type_code: 'AL', allocated: 24, used: 2, pending: 1, available: 21 }]), year: 2026, breakdown: [{ leave_type_name: 'Annual leave', allocated: 24, used: 2, pending: 1 }] },
  'employees': paged([emp]), 'employees/901': emp,
  'org/organization': { id: 1, name: 'Preview Organization', short_name: 'PREVIEW' },
  'employees/901/work-history': paged([{ id: 1, from_date: '2025-01-01', remarks: 'Synthetic preview history' }]),
  'org/units': paged([{ id: 1, name: 'Preview unit', code: 'PREVIEW', is_active: true }]),
  'org/departments': paged([{ id: 1, name: 'Preview department', code: 'PREVIEW', unit_id: 1, is_active: true }]),
  'designations': paged([{ id: 1, name: 'Preview designation', is_active: true }]),
  'attendance': paged([{ id: 1, employee_id: 901, employee_name: 'Preview Employee', attendance_date: day, status: 'PRESENT', worked_minutes: 480, overtime_minutes: 30, late_minutes: 0, early_exit_minutes: 0 }]),
  'attendance/employee/901/calendar': [],
  'attendance/employee/901/summary': { total_present: 18, total_absent: 1, total_leave: 2, total_overtime_minutes: 240, total_working_days: 22, attendance_percentage: 87.5 },
  'leaves/types': paged([{ id: 1, name: 'Annual leave', code: 'AL', is_paid: true, annual_allocation: 24, requires_approval: true, is_active: true }]),
  'leaves/balance/employee/901': [{ employee_id: 901, leave_type_id: 1, leave_type_name: 'Annual leave', allocated: 24, used: 2, pending: 1, available: 21 }],
  'leaves': paged([leave]), 'work-arrangements': paged([{ ...leave, arrangement_type: 'WORK_FROM_HOME' }]),
  'overtime/employee/901/summary': { total_calculated_minutes: 240, total_approved_minutes: 180, pending_count: 1 },
  'overtime': { ...paged([{ id: 1, employee_id: 901, employee_name: 'Preview Employee', attendance_date: day, calculated_minutes: 60, approved_minutes: 30, status: 'PENDING' }]), summary: { total_calculated_minutes: 240, total_approved_minutes: 180, pending_count: 1 } },
  'shifts': paged([{ id: 1, name: 'Preview shift', start_time: '09:00', end_time: '18:00', grace_minutes: 10, break_minutes: 60, is_active: true }]),
  'shifts/assignments': paged([{ id: 1, employee_id: 901, employee_name: 'Preview Employee', shift_name: 'Preview shift', effective_from: day, status: 'ACTIVE' }]),
  'holidays/lists': paged([{ id: 1, name: 'Preview calendar', from_date: '2026-01-01', to_date: '2026-12-31', weekly_off_day: 'SUNDAY', is_default: true, holidays: [{ id: 1, name: 'Preview holiday', holiday_date: day, is_weekly_off: false }] }]),
  'notifications': paged([{ id: 1, notification_id: 1, notification_type: 'attendance', title: 'Preview notification', message: 'Synthetic preview update', created_at: `${day}T09:00:00Z`, is_read: false }]),
  'notifications/unread-count': { unread_count: 1 }, 'auth/mfa/status': { enabled: false, recovery_codes_remaining: 0 }, 'auth/sessions': []
}
async function setup(page: Page, workspace = 'HR', overrides: Record<string, unknown> = {}) {
  await page.route('**/api/session/me', r => r.fulfill({ status: 401, json: {} }))
  await page.route('**/api/session/login', r => r.fulfill({ json: { ...user, ...overrides } }))
  await page.route('**/api/hrms/**', async (r) => {
    const u = new URL(r.request().url())
    const path = u.pathname.replace('/api/hrms/', '').replace(/\/$/, '')
    let json = fixtures[path] ?? paged([])
    if (path === 'dashboard/owner') json = { from_date: u.searchParams.get('from_date'), to_date: u.searchParams.get('to_date'), attendance_last_synced_at: `${day}T09:00:00Z`, summary: { active_headcount: 24, present: 21, absent: 1, on_leave: 2, attendance_rate: 87.5, late_or_missed_punches: 1, pending_requests: 1, approved_overtime_minutes: 240 }, trend: [{ date: day, present: 21, absent: 1, on_leave: 2, weekly_off_or_holiday: 0 }], units: [org], departments: [{ ...org, name: 'Preview department' }] }
    if (path === 'dashboard/owner/exceptions') json = { ...paged([emp]), page: Number(u.searchParams.get('page') || 1), total: 26, total_pages: 2 }
    await r.fulfill({ json: r.request().method() === 'GET' ? json : { ...leave, ok: true } })
  })
  await page.goto(`${workspace === 'TECHNICAL' ? '/admin/login' : '/login'}?redirect=${encodeURIComponent(`/?workspace=${workspace}`)}`)
  await page.waitForFunction(() => (document.querySelector('#__nuxt') as Element & { __vue_app__?: { config: { globalProperties: { $nuxt?: { isHydrating: boolean } } } } })?.__vue_app__?.config.globalProperties.$nuxt?.isHydrating === false)
  await page.getByLabel(workspace === 'TECHNICAL' ? 'Technical username' : 'Mobile number or username').fill('preview')
  await page.getByLabel('Password', { exact: true }).fill('synthetic-password')
  await page.getByRole('button', { name: workspace === 'TECHNICAL' ? 'Sign in to administration' : 'Sign in', exact: true }).click()
  await expect(page.locator('.dashboard-summary dd').first()).toContainText(/\d/)
  await page.addStyleTag({ content: '#nuxt-devtools-container{display:none!important}' })
  await expect(page.locator('.nuxt-loading-indicator')).toHaveCSS('opacity', '0')
}
async function visit(page: Page, name: string) {
  await page.locator('.platform-header').getByRole('button', { name: 'Search pages', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name, exact: true }).click()
  await expect(page.locator('[role=dialog]')).toHaveCount(0)
  await expect(page.locator('.nuxt-loading-indicator')).toHaveCSS('opacity', '0')
}
const routes = ['Dashboard', 'Employees', 'Attendance', 'Leave management', 'Work arrangements', 'Overtime', 'Approvals', 'Shifts', 'Holidays', 'Organization', 'Reports', 'Notifications', 'Profile', 'Settings']
for (const theme of ['light', 'dark'] as const) for (const width of [360, 390, 768, 1366, 1920]) {
  test(`frontend all pages ${width} ${theme}`, async ({ page }) => {
    test.setTimeout(180000)
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize({ width, height: 900 })
    const errors: string[] = []
    page.on('pageerror', e => errors.push(e.message))
    await setup(page)
    for (const name of routes) {
      if (name !== 'Dashboard') await visit(page, name)
      await expect(page.locator('.people-page')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name} ${width}`).toBe(true)
      expect(errors, name).toEqual([])
      if (width === 390 || width === 1366) {
        await page.addStyleTag({ content: '#nuxt-devtools-container{display:none!important}' })
        await page.screenshot({ path: `test-results/auth/frontend-${name.replaceAll(' ', '-')}-${width}-${theme}.png`, fullPage: true })
      }
      if (name === 'Employees') {
        await page.locator('.people-page').getByRole('link', { name: /Preview Employee/ }).first().click()
        await expect(page.locator('.people-page h1')).toContainText('Preview Employee')
        if (width === 390 || width === 1366) await page.screenshot({ path: `test-results/auth/frontend-Employee-details-${width}-${theme}.png`, fullPage: true })
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      }
    }
  })
}
test('frontend search clear/reset and optional selection', async ({ page }) => {
  await setup(page)
  await visit(page, 'Employees')
  const search = page.getByRole('textbox', { name: 'Search', exact: true })
  await search.fill('Preview')
  await page.getByRole('button', { name: 'Clear search', exact: true }).click()
  await expect(search).toHaveValue('')
  await expect(search).toBeFocused()
  await page.getByRole('button', { name: 'All units', exact: true }).click()
  await page.getByRole('option', { name: 'Preview unit', exact: true }).click()
  await page.getByRole('button', { name: 'Clear All units' }).click()
  await expect(page).not.toHaveURL(/unit_id=1/)
  await search.fill('Preview')
  await page.getByRole('button', { name: 'Reset filters' }).click()
  await expect(search).toHaveValue('')
})
test('executive validation, clear/reset and exception pagination', async ({ page }) => {
  await setup(page, 'EXECUTIVE', { business_role: 'ORGANIZATION_OWNER', scope_type: 'ORGANIZATION', permissions: [...permissions, 'dashboard.view_organization'] })
  for (const theme of ['light', 'dark'] as const) for (const width of [360, 390, 768, 1366, 1920]) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (width === 390 || width === 1366) await page.screenshot({ path: `test-results/auth/dashboard-EXECUTIVE-${width}-${theme}.png`, fullPage: true })
  }
  await page.getByLabel('Analytics start date').fill('2099-01-01')
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Reset filters' }).click()
  await page.getByRole('button', { name: 'All units', exact: true }).click()
  await page.getByRole('option', { name: 'Preview unit', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Department performance' })).toBeVisible()
  await page.getByRole('button', { name: 'Clear unit', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Unit performance' })).toBeVisible()
  for (const name of [/absent on/, /late or missed punches/, /employees on leave/, /pending requests/]) {
    const trigger = page.locator('.dashboard-attention').getByRole('button', { name })
    await trigger.click()
    await expect(page.getByRole('dialog').getByRole('link', { name: /Preview Employee/ })).toBeVisible()
    await page.getByRole('dialog').getByRole('button', { name: 'Next', exact: true }).click()
    await expect(page.getByRole('dialog').getByText(/Page 2 of 2/)).toBeVisible()
    await page.getByRole('button', { name: 'Close exceptions' }).click()
    await expect(trigger).toBeFocused()
  }
})
for (const [workspace, overrides] of [['MY', { role: 'EMPLOYEE', business_role: null, permissions: ['attendance.view_self', 'leave.apply'] }], ['TEAM', { business_role: 'DEPARTMENT_MANAGER', scope_type: 'DEPARTMENT', permissions: permissions.filter(p => !['leave.manage', 'work_arrangement.manage', 'attendance.process', 'attendance.correct', 'designation.view', 'shift.assign'].includes(p)) }], ['HR', { scope_type: 'ORGANIZATION' }], ['TECHNICAL', { is_superuser: true, role: 'SUPER_ADMIN', business_role: null, permissions: [] }]] as const) {
  test(`dashboard role ${workspace}`, async ({ page }) => {
    test.setTimeout(120000)
    await setup(page, workspace, overrides)
    for (const theme of ['light', 'dark'] as const) for (const width of [360, 390, 768, 1366, 1920]) {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.setViewportSize({ width, height: 900 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      if (width === 390 || width === 1366) await page.screenshot({ path: `test-results/auth/dashboard-${workspace}-${width}-${theme}.png`, fullPage: true })
    }
    if (workspace === 'MY') await expect(page.getByRole('heading', { name: 'Your shifts' })).toBeVisible()
    if (workspace === 'TEAM') await expect(page.getByText('Department members', { exact: true })).toBeVisible()
    if (workspace === 'HR') await expect(page.getByText('Organization members', { exact: true })).toBeVisible()
    if (workspace === 'TECHNICAL') await expect(page.getByRole('heading', { name: 'Your shifts' })).toHaveCount(0)
  })
}

test('frontend failed refresh retains records, retry and empty results stay distinct', async ({ page }) => {
  await setup(page)
  await visit(page, 'Employees')
  await page.route('**/api/hrms/employees/?**', r => r.fulfill({ status: 503, json: { detail: 'Synthetic failure' } }))
  await page.getByRole('textbox', { name: 'Search', exact: true }).fill('failure')
  await expect(page.getByText('Showing results from the last successful update.', { exact: false })).toBeVisible()
  await expect(page.locator('.people-page').getByRole('link', { name: /Preview Employee/ }).first()).toBeVisible()
  await page.unroute('**/api/hrms/employees/?**')
  await page.getByRole('button', { name: 'Refresh people' }).click()
  await expect(page.getByText('Showing results from the last successful update.', { exact: false })).toHaveCount(0)
  await page.route('**/api/hrms/employees/?**', r => r.fulfill({ json: paged([]) }))
  await page.getByRole('textbox', { name: 'Search', exact: true }).fill('no matching results')
  await expect(page.locator('.people-page').getByRole('link', { name: /Preview Employee/ })).toHaveCount(0)
  await expect(page.getByText('No employees found', { exact: true })).toBeVisible()
})

test('frontend security password visibility and keyboard enlargement', async ({ page }) => {
  await setup(page)
  await visit(page, 'Settings')
  await expect(page.getByRole('button', { name: 'Show password', exact: true }).first()).toBeVisible()
  await page.getByLabel('Current password', { exact: true }).first().fill('synthetic-password')
  await page.getByRole('button', { name: 'Show password', exact: true }).first().click()
  await expect(page.getByLabel('Current password', { exact: true }).first()).toHaveAttribute('type', 'text')
  await page.setViewportSize({ width: 360, height: 900 })
  await page.addStyleTag({ content: 'html{font-size:200%}' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('self-service Nuxt UI forms validate, submit once and restore focus', async ({ page }) => {
  await setup(page, 'MY', { role: 'EMPLOYEE', business_role: null, permissions: ['attendance.view_self', 'leave.apply', 'leave.view_self', 'work_arrangement.apply'] })
  for (const [destination, triggerName, title, minimum] of [['Leave', 'Request leave', 'Request leave', 3], ['Work arrangements', 'New request', 'Request work from home', 5]] as const) {
    await visit(page, destination)
    const trigger = page.getByRole('button', { name: triggerName, exact: true }).first()
    await trigger.click()
    const dialog = page.getByRole('dialog', { name: title })
    await expect(dialog).toBeVisible()
    const submit = dialog.getByRole('button', { name: 'Submit request' })
    await expect(submit).toBeDisabled()
    await dialog.getByLabel('Reason', { exact: true }).fill('a')
    await expect(dialog.getByText(`Enter at least ${minimum} characters.`)).toBeVisible()
    await dialog.getByLabel('Reason', { exact: true }).fill('Synthetic request for frontend testing')
    await expect(submit).toBeEnabled()
    await submit.click()
    await expect(page.locator('[role=dialog]')).toHaveCount(0)
    await expect(trigger).toBeFocused()
  }
})

test('approval rejection keeps existing validation and explicit cancellation', async ({ page }) => {
  await setup(page)
  await visit(page, 'Approvals')
  await page.getByRole('button', { name: 'Reject', exact: true }).first().click()
  const dialog = page.getByRole('dialog', { name: 'Reject request', exact: true })
  await dialog.getByLabel('Rejection reason').fill('a')
  await expect(dialog.getByRole('button', { name: 'Reject request', exact: true })).toBeDisabled()
  await dialog.getByLabel('Rejection reason').fill('Synthetic reason')
  await expect(dialog.getByRole('button', { name: 'Reject request', exact: true })).toBeEnabled()
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.locator('[role=dialog]')).toHaveCount(0)
})

test('dependent filters, rows per page and notification actions', async ({ page }) => {
  await setup(page)
  await visit(page, 'Employees')
  await page.getByRole('button', { name: 'All units', exact: true }).click()
  await page.getByRole('option', { name: 'Preview unit', exact: true }).click()
  await page.getByRole('button', { name: 'All departments', exact: true }).click()
  await page.getByRole('option', { name: 'Preview department', exact: true }).click()
  await page.getByRole('button', { name: 'Clear All units' }).click()
  await expect(page).not.toHaveURL(/department_id=1/)
  await page.getByLabel('Rows per page', { exact: true }).click()
  await page.getByRole('option', { name: '10', exact: true }).click()
  await expect(page).toHaveURL(/page_size=10/)
  await expect(page).not.toHaveURL(/page=2/)
  await visit(page, 'Notifications')
  await page.getByRole('button', { name: 'Mark all read', exact: true }).click()
  await expect(page.getByText('All caught up')).toBeVisible()
})

test('report tabs retain data alternatives and labeled period controls', async ({ page }) => {
  await setup(page)
  await visit(page, 'Reports')
  await expect(page.getByLabel('Month', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: /Attendance comparison table/ })).toBeVisible()
  await page.getByRole('button', { name: 'Leave summary', exact: true }).click()
  await expect(page.getByLabel('Year', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Leave allocation and usage' })).toBeVisible()
  await expect(page.locator('.people-page').getByText('Preview Employee').first()).toBeVisible()
})
