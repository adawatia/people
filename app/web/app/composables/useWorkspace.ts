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

const WORKSPACE_KEYS = new Set<Workspace>(WORKSPACES.map(workspace => workspace.key))

export function workspacesForUser(user: CurrentUser | null): Workspace[] {
  if (!user) return []
  if (user.is_superuser) return ['TECHNICAL']

  const permissions = new Set(user.permissions || [])
  const workspaces: Workspace[] = ['MY']
  if (['attendance.view_department', 'leave.approve', 'work_arrangement.approve', 'overtime.view_department'].some(permission => permissions.has(permission)) && !permissions.has('leave.manage') && !permissions.has('dashboard.view_organization')) {
    workspaces.push('TEAM')
  }
  if (['employee.create', 'employee.update', 'leave.manage', 'attendance.process', 'work_arrangement.manage', 'system.configure'].some(permission => permissions.has(permission))) {
    workspaces.push('HR')
  }
  if (permissions.has('dashboard.view_organization')) workspaces.push('EXECUTIVE')
  return workspaces
}

export function useWorkspace() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuth()
  const selected = useState<Workspace | null>('active-workspace', () => null)
  const available = computed(() => workspacesForUser(auth.user.value))
  const requested = computed(() => String(route.query.workspace || '').toUpperCase() as Workspace)
  const current = computed<Workspace>(() => {
    if (WORKSPACE_KEYS.has(requested.value) && available.value.includes(requested.value)) return requested.value
    if (selected.value && available.value.includes(selected.value)) return selected.value
    return available.value[0] || 'MY'
  })
  const definition = computed(() => WORKSPACES.find(workspace => workspace.key === current.value) || WORKSPACES[0]!)

  watch(current, (value) => {
    selected.value = value
  }, { immediate: true })
  watch(() => auth.user.value?.id, () => {
    if (!auth.user.value || !available.value.includes(selected.value as Workspace)) selected.value = available.value[0] || null
  }, { immediate: true })

  async function select(workspace: Workspace, path = route.path) {
    if (!available.value.includes(workspace)) return
    selected.value = workspace
    await router.push({ path, query: { ...route.query, workspace } })
  }

  function link(path: string) {
    return { path, query: { ...route.query, workspace: current.value } }
  }

  return { available, current, definition, select, link }
}
