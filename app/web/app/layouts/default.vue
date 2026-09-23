<script setup lang="ts">
import { WORKSPACES, type Workspace } from '~/composables/useWorkspace'
/**
 * Application shell: sidebar navigation, top bar and content slot.
 *
 * Navigation is grouped by the active workspace and filtered by permissions.
 * Items without permission codes are shared/self-service pages. Technical
 * admins (superuser) get a dedicated technical workspace.
 *
 * The gate is presentation only — every endpoint re-checks permission and row
 * scope, so a hidden link is convenience, never security.
 */
interface NavItem { label: string, icon: string, to: string, iconTone?: string, permissions?: string[] }
const route = useRoute()
const auth = useAuth()
const workspace = useWorkspace()
const availableWorkspaces = workspace.available
const currentWorkspace = workspace.current
const workspaceDefinition = computed(() => workspace.definition.value || WORKSPACES[0]!)
const mobileOpen = ref(false)
const mobileGroup = ref('More')
const isTechnicalAdmin = computed(() => Boolean(auth.user.value?.is_superuser))
const navByWorkspace: Record<string, NavItem[]> = {
  MY: [
    { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue' },
    { label: 'Attendance', icon: 'i-lucide-calendar-check-2', to: '/attendance', iconTone: 'people-icon--blue' },
    { label: 'Leave', icon: 'i-lucide-calendar-days', to: '/leaves', iconTone: 'people-icon--lavender' },
    { label: 'Work arrangements', icon: 'i-lucide-briefcase-business', to: '/work-arrangements', iconTone: 'people-icon--peach' },
    { label: 'Overtime', icon: 'i-lucide-timer', to: '/overtime', iconTone: 'people-icon--yellow' },
    { label: 'Shifts', icon: 'i-lucide-clock-3', to: '/shifts', iconTone: 'people-icon--blue' },
    { label: 'Holidays', icon: 'i-lucide-calendar-heart', to: '/holidays', iconTone: 'people-icon--lavender' }
  ],
  TEAM: [
    { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue' },
    { label: 'Employees', icon: 'i-lucide-users-round', to: '/employees', iconTone: 'people-icon--mint', permissions: ['employee.view'] },
    { label: 'Attendance', icon: 'i-lucide-calendar-check-2', to: '/attendance', iconTone: 'people-icon--blue', permissions: ['attendance.view_department'] },
    { label: 'Leave approvals', icon: 'i-lucide-calendar-days', to: '/leaves', iconTone: 'people-icon--lavender', permissions: ['leave.approve'] },
    { label: 'Work arrangements', icon: 'i-lucide-briefcase-business', to: '/work-arrangements', iconTone: 'people-icon--peach', permissions: ['work_arrangement.approve'] },
    { label: 'Overtime', icon: 'i-lucide-timer', to: '/overtime', iconTone: 'people-icon--yellow', permissions: ['overtime.view_department'] },
    { label: 'Approvals', icon: 'i-lucide-clipboard-check', to: '/approvals', iconTone: 'people-icon--rose', permissions: ['leave.approve', 'work_arrangement.approve', 'overtime.approve'] },
    { label: 'Reports', icon: 'i-lucide-chart-no-axes-combined', to: '/reports', iconTone: 'people-icon--yellow', permissions: ['reports.attendance', 'reports.leave'] }
  ],
  HR: [
    { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue' },
    { label: 'Employees', icon: 'i-lucide-users-round', to: '/employees', iconTone: 'people-icon--mint', permissions: ['employee.view'] },
    { label: 'Attendance', icon: 'i-lucide-calendar-check-2', to: '/attendance', iconTone: 'people-icon--blue', permissions: ['attendance.view', 'attendance.view_unit', 'attendance.process'] },
    { label: 'Leave management', icon: 'i-lucide-calendar-days', to: '/leaves', iconTone: 'people-icon--lavender', permissions: ['leave.manage', 'leave.approve'] },
    { label: 'Work arrangements', icon: 'i-lucide-briefcase-business', to: '/work-arrangements', iconTone: 'people-icon--peach', permissions: ['work_arrangement.manage', 'work_arrangement.approve'] },
    { label: 'Overtime', icon: 'i-lucide-timer', to: '/overtime', iconTone: 'people-icon--yellow', permissions: ['overtime.view_department', 'overtime.approve'] },
    { label: 'Approvals', icon: 'i-lucide-clipboard-check', to: '/approvals', iconTone: 'people-icon--rose', permissions: ['leave.approve', 'work_arrangement.approve', 'overtime.approve'] },
    { label: 'Shifts', icon: 'i-lucide-clock-3', to: '/shifts', iconTone: 'people-icon--blue', permissions: ['shift.assign', 'shift.update'] },
    { label: 'Holidays', icon: 'i-lucide-calendar-heart', to: '/holidays', iconTone: 'people-icon--lavender' },
    { label: 'Organization', icon: 'i-lucide-building-2', to: '/organization', iconTone: 'people-icon--mint', permissions: ['designation.view', 'employee.view'] },
    { label: 'Reports', icon: 'i-lucide-chart-no-axes-combined', to: '/reports', iconTone: 'people-icon--yellow', permissions: ['reports.view', 'reports.attendance', 'reports.leave'] }
  ],
  EXECUTIVE: [
    { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue', permissions: ['dashboard.view_organization'] },
    { label: 'Reports', icon: 'i-lucide-chart-no-axes-combined', to: '/reports', iconTone: 'people-icon--yellow', permissions: ['reports.view', 'reports.attendance', 'reports.leave'] },
    { label: 'Organization', icon: 'i-lucide-building-2', to: '/organization', iconTone: 'people-icon--mint', permissions: ['employee.view'] }
  ],
  TECHNICAL: [{ label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue' }]
}
const visibleItems = computed(() => (navByWorkspace[workspace.current.value] || []).filter(item => !item.permissions || item.permissions.some(auth.hasPermission)))
const navSections = computed(() => {
  const groups = new Map<string, NavItem[]>()
  for (const item of visibleItems.value) {
    let group: string
    if (workspace.current.value === 'MY') group = 'My work'
    else if (workspace.current.value === 'TEAM') {
      group = item.to === '/' ? 'Overview' : ['/employees', '/attendance'].includes(item.to) ? 'Team' : ['/leaves', '/work-arrangements', '/approvals'].includes(item.to) ? 'Requests & approvals' : 'Insights'
    } else if (workspace.current.value === 'HR') {
      group = item.to === '/' ? 'Overview' : ['/employees', '/attendance'].includes(item.to) ? 'Workforce' : ['/leaves', '/work-arrangements', '/approvals'].includes(item.to) ? 'Requests & approvals' : item.to === '/overtime' ? 'Time & compensation' : ['/shifts', '/holidays', '/organization'].includes(item.to) ? 'Organization' : 'Insights'
    } else if (workspace.current.value === 'EXECUTIVE') group = item.to === '/' ? 'Overview' : 'Insights'
    else group = 'Administration'

    const items = groups.get(group) || []
    items.push(item)
    groups.set(group, items)
  }
  return Array.from(groups, ([label, items]) => ({ label, items }))
})
const pageTitle = computed(() => {
  if (route.path === '/settings') return isTechnicalAdmin.value ? 'System administration' : 'Security settings'
  if (route.path === '/profile') return 'Profile'
  return visibleItems.value.find(item => item.to === route.path)?.label || workspaceDefinition.value.label || 'People'
})
const accountItems: NavItem[] = [
  { label: 'Profile', icon: 'i-lucide-user-round', to: '/profile' },
  { label: 'Settings', icon: 'i-lucide-settings', to: '/settings' },
  { label: 'Notifications', icon: 'i-lucide-bell', to: '/notifications' }
]
const mobileGroups = computed(() => {
  const itemsFor = (...paths: string[]) => visibleItems.value.filter(item => paths.includes(item.to))
  if (isTechnicalAdmin.value) return [
    { label: 'Home', icon: 'i-lucide-house', items: itemsFor('/') },
    { label: 'Profile', icon: 'i-lucide-user-round', items: [accountItems[0]!] },
    { label: 'Settings', icon: 'i-lucide-settings', items: [accountItems[1]!] },
    { label: 'Updates', icon: 'i-lucide-bell', items: [accountItems[2]!] }
  ]
  if (currentWorkspace.value === 'EXECUTIVE') return [
    { label: 'Home', icon: 'i-lucide-house', items: itemsFor('/') },
    { label: 'Reports', icon: 'i-lucide-chart-no-axes-combined', items: itemsFor('/reports') },
    { label: 'Company', icon: 'i-lucide-building-2', items: itemsFor('/organization') },
    { label: 'Account', icon: 'i-lucide-user-round', items: accountItems }
  ]
  return [
    { label: 'Home', icon: 'i-lucide-house', items: itemsFor('/') },
    { label: 'Time', icon: 'i-lucide-clock-3', items: itemsFor('/attendance', '/overtime', '/shifts') },
    { label: 'Requests', icon: 'i-lucide-clipboard-check', items: itemsFor('/leaves', '/work-arrangements', '/approvals') },
    currentWorkspace.value === 'MY'
      ? { label: 'Calendar', icon: 'i-lucide-calendar-days', items: itemsFor('/holidays') }
      : { label: 'People', icon: 'i-lucide-users-round', items: itemsFor('/employees', '/organization') }
  ]
})
const mobileSheetItems = computed(() => mobileGroup.value === 'More'
  ? [...visibleItems.value.filter(item => !mobileGroups.value.some(group => group.items.some(primary => primary.to === item.to))), ...accountItems]
  : mobileGroups.value.find(group => group.label === mobileGroup.value)?.items || [])
function openMobileGroup(label: string) {
  mobileGroup.value = label
  mobileOpen.value = true
}
async function changeWorkspace(event: Event) {
  const next = (event.target as HTMLSelectElement).value as Workspace
  await workspace.select(next)
}
watch(() => route.fullPath, () => {
  // Navigating should always collapse the mobile drawer.
  mobileOpen.value = false
})
onMounted(() => {
  const desktop = window.matchMedia('(min-width: 1024px)')
  const closeOnDesktop = () => {
    if (desktop.matches) mobileOpen.value = false
  }
  desktop.addEventListener('change', closeOnDesktop)
  onBeforeUnmount(() => desktop.removeEventListener('change', closeOnDesktop))
})
</script>

<template>
  <div class="min-h-dvh bg-[var(--people-canvas)]">
    <aside
      class="fixed inset-y-0 left-0 z-50 hidden w-[17rem] flex-col border-r border-[var(--people-border)] bg-[var(--people-surface)] px-4 py-5 lg:flex"
    >
      <div class="flex items-center justify-between px-2">
        <BrandMark />
      </div>
      <div
        v-if="availableWorkspaces.length > 1"
        class="mt-6 px-2"
      >
        <label
          for="workspace-switcher"
          class="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted"
        >Workspace</label>
        <div class="relative">
          <select
            id="workspace-switcher"
            :value="currentWorkspace"
            class="w-full appearance-none rounded-xl border border-[var(--people-border)] bg-[var(--people-surface)] px-3 py-2.5 pr-9 text-sm font-semibold text-highlighted outline-none transition focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
            @change="changeWorkspace"
          >
            <option
              v-for="item in availableWorkspaces"
              :key="item"
              :value="item"
            >
              {{ WORKSPACES.find(workspaceItem => workspaceItem.key === item)?.label || item }}
            </option>
          </select>
          <UIcon
            name="i-lucide-chevron-down"
            class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted"
          />
        </div>
        <p class="mt-2 text-xs text-muted">
          {{ workspaceDefinition.description }}
        </p>
      </div>
      <nav
        class="mt-6 flex-1 space-y-5 overflow-y-auto"
        aria-label="Primary navigation"
      >
        <section
          v-for="section in navSections"
          :key="section.label"
          :aria-label="`${section.label} navigation`"
          class="rounded-xl border border-[var(--people-border)] bg-[var(--people-canvas)]/45 p-2"
        >
          <h2 class="mb-1.5 flex items-center gap-2 px-2 py-1 text-[11px] font-bold uppercase tracking-[0.12em] text-highlighted">
            <span class="size-1.5 rounded-full bg-primary" />
            {{ section.label }}
          </h2>
          <NuxtLink
            v-for="item in section.items"
            :key="item.to"
            :to="workspace.link(item.to)"
            class="flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors"
            :class="route.path === item.to || (item.to !== '/' && route.path.startsWith(`${item.to}/`)) ? 'bg-[var(--people-lavender)] text-primary-700 dark:text-primary-300' : 'text-muted hover:bg-muted/10 hover:text-highlighted'"
          >
            <span
              class="people-icon size-8 shrink-0"
              :class="item.iconTone"
            >
              <UIcon
                :name="item.icon"
                class="size-4"
              />
            </span>{{ item.label }}
          </NuxtLink>
        </section>
        <NuxtLink
          v-if="isTechnicalAdmin"
          to="/settings"
          class="flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors"
          :class="route.path === '/settings' ? 'bg-[var(--people-lavender)] text-primary-700 dark:text-primary-300' : 'text-muted hover:bg-muted/10 hover:text-highlighted'"
        >
          <span class="people-icon people-icon--lavender size-8 shrink-0">
            <UIcon
              name="i-lucide-shield-check"
              class="size-4"
            />
          </span>System administration
        </NuxtLink>
      </nav>
      <div class="border-t border-[var(--people-border)] pt-4">
        <NuxtLink
          to="/profile"
          class="flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-muted/10"
        >
          <UAvatar
            :text="auth.initials.value"
            size="md"
          />
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-semibold">
              {{ auth.displayName.value }}
            </p><p class="truncate text-xs text-muted">
              {{ auth.user.value?.employee_code || auth.user.value?.email }}
            </p>
          </div>
          <UButton
            icon="i-lucide-log-out"
            color="neutral"
            variant="ghost"
            aria-label="Sign out"
            @click="auth.logout"
          />
        </NuxtLink>
      </div>
    </aside>
    <div class="lg:pl-[17rem]">
      <header class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-[var(--people-border)] bg-[var(--people-surface)]/90 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
        <h1 class="min-w-0 flex-1 truncate text-base font-semibold">
          {{ pageTitle }}
        </h1>
        <UButton
          icon="i-lucide-search"
          color="neutral"
          variant="ghost"
          aria-label="Search"
        />
        <UButton
          icon="i-lucide-bell"
          color="neutral"
          variant="ghost"
          to="/notifications"
          aria-label="Notifications"
        />
        <UColorModeButton />
      </header>
      <main class="mx-auto w-full max-w-[96rem] px-4 py-6 pb-24 sm:px-6 lg:px-8 lg:py-8 lg:pb-8">
        <slot />
      </main>
    </div>
    <nav
      class="fixed inset-x-0 bottom-0 z-40 border-t border-[var(--people-border)] bg-[var(--people-surface)]/95 px-2 pb-[env(safe-area-inset-bottom)] pt-2 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur-xl lg:hidden"
      aria-label="Mobile navigation"
    >
      <div class="mx-auto flex max-w-lg items-center justify-around gap-1">
        <UButton
          v-for="item in mobileGroups"
          :key="item.label"
          :icon="item.icon"
          :color="item.items.some(link => route.path === link.to) ? 'primary' : 'neutral'"
          variant="ghost"
          size="sm"
          class="min-w-0 flex-1 flex-col gap-0.5 px-1 py-2 text-[10px]"
          :aria-label="item.label"
          aria-haspopup="dialog"
          :aria-expanded="mobileOpen && mobileGroup === item.label"
          @click="openMobileGroup(item.label)"
        >
          {{ item.label }}
        </UButton>
        <UButton
          icon="i-lucide-grid-2x2"
          color="neutral"
          variant="ghost"
          size="sm"
          class="min-w-0 flex-1 flex-col gap-0.5 px-1 py-2 text-[10px]"
          aria-label="More navigation"
          aria-haspopup="dialog"
          :aria-expanded="mobileOpen && mobileGroup === 'More'"
          @click="openMobileGroup('More')"
        >
          More
        </UButton>
      </div>
    </nav>
    <UDrawer
      v-model:open="mobileOpen"
      :title="mobileGroup"
      :description="workspaceDefinition.label"
      direction="bottom"
      close
      :ui="{ content: 'h-[55dvh]', container: 'h-full min-h-0', body: 'overflow-y-auto pb-[env(safe-area-inset-bottom)]' }"
    >
      <template #body>
        <div
          v-if="mobileGroup === 'More' && availableWorkspaces.length > 1"
          class="mb-5"
        >
          <label
            for="mobile-workspace"
            class="mb-2 block text-sm font-semibold"
          >Workspace</label>
          <select
            id="mobile-workspace"
            :value="currentWorkspace"
            class="min-h-11 w-full rounded-xl border border-[var(--people-border)] bg-[var(--people-surface)] px-3 text-sm"
            @change="changeWorkspace"
          >
            <option
              v-for="item in availableWorkspaces"
              :key="item"
              :value="item"
            >
              {{ WORKSPACES.find(definition => definition.key === item)?.label }}
            </option>
          </select>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <NuxtLink
            v-for="item in mobileSheetItems"
            :key="item.to"
            :to="workspace.link(item.to)"
            class="flex min-h-24 flex-col items-start justify-center gap-3 rounded-xl border border-[var(--people-border)] bg-[var(--people-surface)] p-4 text-sm font-semibold"
            :aria-current="route.path === item.to ? 'page' : undefined"
            @click="mobileOpen = false"
          >
            <UIcon
              :name="item.icon"
              class="size-6 text-primary"
            />
            {{ item.label }}
          </NuxtLink>
        </div>
        <p
          v-if="!mobileSheetItems.length"
          class="py-6 text-sm text-muted"
        >
          No pages are available in this section.
        </p>
        <UButton
          v-if="mobileGroup === 'More'"
          class="mt-5 min-h-11"
          icon="i-lucide-log-out"
          color="neutral"
          variant="soft"
          @click="auth.logout"
        >
          Sign out
        </UButton>
      </template>
    </UDrawer>
  </div>
</template>
