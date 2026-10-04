import type { CurrentUser } from '#shared/types/auth'

export type Workspace = 'MY' | 'TEAM' | 'HR' | 'EXECUTIVE' | 'TECHNICAL'

export interface WorkspaceDefinition {
  key: Workspace
  label: string
  shortLabel: string
  description: string
  icon: string
}

export const WORKSPACES: WorkspaceDefinition[] = [
  { key: 'MY', label: 'My Workspace', shortLabel: 'My', description: 'Your attendance, leave and work', icon: 'i-lucide-user-round' },
  { key: 'TEAM', label: 'Team Workspace', shortLabel: 'Team', description: 'Your department and approvals', icon: 'i-lucide-users-round' },
  { key: 'HR', label: 'HR Workspace', shortLabel: 'HR', description: 'People operations in your scope', icon: 'i-lucide-building-2' },
  { key: 'EXECUTIVE', label: 'Executive Workspace', shortLabel: 'Executive', description: 'Organization-wide performance', icon: 'i-lucide-chart-no-axes-combined' },
  { key: 'TECHNICAL', label: 'Technical Administration', shortLabel: 'Admin', description: 'System access and integrations', icon: 'i-lucide-shield-check' }
]

interface WorkspaceRouteRule {
  path: string
  permissions?: string[]
}

const WORKSPACE_ROUTES: Record<Workspace, WorkspaceRouteRule[]> = {
  MY: [
    { path: '/' }, { path: '/attendance', permissions: ['attendance.view_self'] },
    { path: '/leaves', permissions: ['leave.apply'] }, { path: '/work-arrangements', permissions: ['work_arrangement.apply'] },
    { path: '/overtime', permissions: ['overtime.view_self'] }, { path: '/shifts' }, { path: '/holidays' },
    { path: '/profile' }, { path: '/settings' }, { path: '/notifications' }
  ],
  TEAM: [
    { path: '/' }, { path: '/employees', permissions: ['employee.view'] },
    { path: '/attendance', permissions: ['attendance.view_department'] }, { path: '/leaves', permissions: ['leave.approve'] },
    { path: '/work-arrangements', permissions: ['work_arrangement.approve'] }, { path: '/overtime', permissions: ['overtime.view_department'] },
    { path: '/approvals', permissions: ['leave.approve', 'work_arrangement.approve', 'overtime.approve'] },
    { path: '/shifts', permissions: ['shift.view_self'] },
    { path: '/reports', permissions: ['reports.attendance', 'reports.leave', 'reports.view'] },
    { path: '/profile' }, { path: '/settings' }, { path: '/notifications' }
  ],
  HR: [
    { path: '/' }, { path: '/employees', permissions: ['employee.view'] },
    { path: '/attendance', permissions: ['attendance.view', 'attendance.view_unit', 'attendance.process'] },
    { path: '/leaves', permissions: ['leave.manage', 'leave.approve'] },
    { path: '/work-arrangements', permissions: ['work_arrangement.manage', 'work_arrangement.approve'] },
    { path: '/overtime', permissions: ['overtime.view_department', 'overtime.approve'] },
    { path: '/approvals', permissions: ['leave.approve', 'work_arrangement.approve', 'overtime.approve'] },
    { path: '/shifts', permissions: ['shift.assign', 'shift.update'] }, { path: '/holidays' },
    { path: '/organization', permissions: ['designation.view', 'employee.view'] },
    { path: '/reports', permissions: ['reports.attendance', 'reports.leave', 'reports.view'] },
    { path: '/profile' }, { path: '/settings' }, { path: '/notifications' }
  ],
  EXECUTIVE: [
    { path: '/', permissions: ['dashboard.view_organization'] },
    { path: '/reports', permissions: ['reports.attendance', 'reports.leave', 'reports.view'] },
    { path: '/organization', permissions: ['employee.view'] },
    { path: '/profile' }, { path: '/settings' }, { path: '/notifications' }
  ],
  TECHNICAL: [{ path: '/' }, { path: '/organization' }, { path: '/settings' }, { path: '/profile' }, { path: '/notifications' }]
}

// Destinations promoted to the mobile bottom bar, in order. Everything else
// stays in the More drawer, and each path must exist in WORKSPACE_ROUTES above
// so the bar can never promote a page its workspace does not allow.
export const MOBILE_TABS: Record<Workspace, string[]> = {
  MY: ['/attendance', '/leaves'],
  TEAM: ['/approvals', '/attendance'],
  HR: ['/employees', '/approvals', '/attendance'],
  EXECUTIVE: ['/reports', '/organization'],
  TECHNICAL: ['/settings']
}

// Home, Workspace and More occupy three of the five bar slots, so a switcher
// leaves room for two role destinations and a single-workspace account for
// three. Keeping the cap here keeps the bar at five slots either way.
export function mobileTabPaths(workspace: Workspace, withSwitcher: boolean): string[] {
  return MOBILE_TABS[workspace].slice(0, withSwitcher ? 2 : 3)
}

export function workspacesForUser(user: CurrentUser | null): Workspace[] {
  if (!user) return []
  if (user.is_superuser) return ['TECHNICAL']

  const permissions = new Set(user.permissions || [])
  const workspaces: Workspace[] = ['MY']
  if (
    ['attendance.view_department', 'leave.approve', 'work_arrangement.approve', 'overtime.view_department', 'overtime.approve'].some(permission => permissions.has(permission))
    && !permissions.has('leave.manage')
    && !permissions.has('dashboard.view_organization')
  ) {
    workspaces.push('TEAM')
  }
  if ([
    'user.view', 'user.create', 'user.update', 'user.deactivate',
    'employee.create', 'employee.update', 'employee.deactivate',
    'designation.view', 'designation.create', 'designation.update', 'designation.delete',
    'leave.manage', 'attendance.process', 'attendance.correct',
    'work_arrangement.manage', 'shift.assign', 'shift.update', 'system.configure', 'audit.view',
    'salary_cost.view_unit', 'salary_cost.view_department'
  ].some(permission => permissions.has(permission))) {
    workspaces.push('HR')
  }
  if (permissions.has('dashboard.view_organization')) workspaces.push('EXECUTIVE')
  return workspaces
}

export function resolveWorkspace(user: CurrentUser | null, requested: unknown, saved: unknown): Workspace {
  const available = workspacesForUser(user)
  const query = typeof requested === 'string' ? requested.toUpperCase() as Workspace : undefined
  if (query && available.includes(query)) return query
  if (typeof saved === 'string' && available.includes(saved as Workspace)) return saved as Workspace
  return available[0] || 'MY'
}

export function canVisitWorkspace(user: CurrentUser | null, workspace: Workspace, path: string): boolean {
  if (!workspacesForUser(user).includes(workspace)) return false
  const rule = WORKSPACE_ROUTES[workspace].find(candidate => candidate.path === path || (candidate.path !== '/' && path.startsWith(`${candidate.path}/`)))
  return Boolean(rule && (!rule.permissions || rule.permissions.some(permission => user?.is_superuser || user?.permissions?.includes(permission))))
}

export function useWorkspace() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuth()
  // This is a presentation preference only. Persisting it lets a refresh on an
  // internal page keep the selected workspace; availability is recalculated
  // from current permissions below on every app load.
  const selected = useCookie<Workspace | null>('people_workspace', { maxAge: 60 * 60 * 24 * 365, sameSite: 'lax' })
  const available = computed(() => workspacesForUser(auth.user.value))
  const current = computed(() => resolveWorkspace(auth.user.value, route.query.workspace, selected.value))
  const definition = computed(() => WORKSPACES.find(workspace => workspace.key === current.value) || WORKSPACES[0]!)

  function canVisit(path: string, inWorkspace = current.value) {
    return canVisitWorkspace(auth.user.value, inWorkspace, path)
  }

  watch(current, (value) => {
    selected.value = value
  }, { immediate: true })
  watch(() => auth.user.value?.id, () => {
    if (!auth.user.value || !available.value.includes(selected.value as Workspace)) selected.value = available.value[0] || null
  }, { immediate: true })

  async function select(workspace: Workspace, path = route.path) {
    if (!available.value.includes(workspace)) return
    selected.value = workspace
    await router.push({ path: canVisit(path, workspace) ? path : '/', query: { workspace } })
  }

  function link(path: string) {
    return { path, query: { workspace: current.value } }
  }

  return { available, current, definition, select, link, canVisit }
}
