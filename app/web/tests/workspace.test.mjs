import assert from 'node:assert/strict'
import test from 'node:test'
import { MOBILE_TABS, canVisitWorkspace, mobileTabPaths, resolveWorkspace, workspacesForUser } from '../app/composables/useWorkspace.ts'

const employee = { permissions: ['attendance.view_self', 'leave.apply', 'work_arrangement.apply', 'overtime.view_self', 'shift.view_self'] }
const manager = { permissions: [...employee.permissions, 'employee.view', 'attendance.view_department', 'overtime.approve'] }
const hr = { permissions: [...manager.permissions, 'leave.manage', 'attendance.process'] }
const owner = { permissions: [...employee.permissions, 'employee.view', 'attendance.view', 'attendance.view_unit', 'attendance.view_department', 'overtime.view_department', 'dashboard.view_organization'] }
const executive = { permissions: ['reports.view', 'employee.view', 'dashboard.view_organization'] }
const technical = { is_superuser: true, permissions: [] }

test('workforce roles add only their appropriate workspaces', () => {
  assert.deepEqual(workspacesForUser(employee), ['MY'])
  assert.deepEqual(workspacesForUser(manager), ['MY', 'TEAM'])
  assert.deepEqual(workspacesForUser(hr), ['MY', 'HR'])
  assert.deepEqual(workspacesForUser(owner), ['MY', 'EXECUTIVE'])
  assert.deepEqual(workspacesForUser({ is_superuser: true }), ['TECHNICAL'])
  assert.deepEqual(workspacesForUser(null), [])
})

test('destination workspace wins over the saved preference during navigation', () => {
  assert.equal(resolveWorkspace(hr, 'HR', 'MY'), 'HR')
  assert.equal(resolveWorkspace(hr, 'MY', 'HR'), 'MY')
  assert.equal(resolveWorkspace(employee, 'HR', 'HR'), 'MY')
  assert.equal(resolveWorkspace(hr, ['HR', 'MY'], 'MY'), 'MY')
})

test('personal and management routes stay separate and approvals accept overtime alone', () => {
  assert.equal(canVisitWorkspace(manager, 'MY', '/employees'), false)
  assert.equal(canVisitWorkspace(manager, 'TEAM', '/employees/42'), true)
  assert.equal(canVisitWorkspace(manager, 'TEAM', '/approvals'), true)
  assert.equal(canVisitWorkspace(employee, 'MY', '/shifts'), true)
  assert.equal(canVisitWorkspace(manager, 'TEAM', '/shifts'), true)
  assert.equal(canVisitWorkspace(employee, 'TEAM', '/approvals'), false)
  assert.equal(canVisitWorkspace(owner, 'HR', '/attendance'), false)
  assert.equal(canVisitWorkspace(technical, 'TECHNICAL', '/organization'), true)
  assert.equal(canVisitWorkspace(employee, 'TECHNICAL', '/organization'), false)
})

test('mobile bar promotes only destinations its role can open', () => {
  const mobileUsers = { MY: employee, TEAM: manager, HR: hr, EXECUTIVE: executive, TECHNICAL: technical }
  for (const [workspace, paths] of Object.entries(MOBILE_TABS)) {
    for (const path of paths) {
      assert.equal(canVisitWorkspace(mobileUsers[workspace], workspace, path), true, `${workspace} ${path}`)
    }
    const accountPaths = workspace === 'TECHNICAL' ? ['/', '/profile', '/notifications'] : ['/', '/profile', '/settings', '/notifications']
    assert.ok(accountPaths.every(reserved => !paths.includes(reserved)), `${workspace} leaves account pages in More`)
    assert.ok(mobileTabPaths(workspace, true).length <= 2, `${workspace} fits five slots with a workspace tab`)
    assert.ok(mobileTabPaths(workspace, false).length <= 3, `${workspace} fits five slots without a workspace tab`)
  }
  assert.equal(mobileTabPaths('HR', true).length, 2)
  assert.equal(mobileTabPaths('HR', false).length, 3)
})
