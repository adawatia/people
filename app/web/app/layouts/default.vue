<script setup lang="ts">
import { mobileTabPaths, WORKSPACES, type Workspace } from '~/composables/useWorkspace'
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
const sidebarCollapsed = useCookie<boolean>('people_sidebar_collapsed', { default: () => false, maxAge: 60 * 60 * 24 * 365, sameSite: 'lax' })
const signingOut = ref(false)
const toast = useToast()
const collapsedWorkspaceItems = computed(() => availableWorkspaces.value.map(key => ({
  label: WORKSPACES.find(item => item.key === key)?.label || key,
  icon: WORKSPACES.find(item => item.key === key)?.icon,
  trailingIcon: key === currentWorkspace.value ? 'i-lucide-check' : undefined,
  onSelect: () => workspace.select(key)
})))
async function signOut() {
  if (signingOut.value) return
  signingOut.value = true
  try {
    await auth.logout()
  } catch {
    toast.add({ title: 'Could not sign out', description: 'Please try again.', color: 'error' })
  } finally {
    signingOut.value = false
  }
}
const mobileOpen = ref(false)
const mobileGroup = ref('More')
const globalSearchOpen = ref(false)
const globalSearchQuery = ref('')
const isTechnicalAdmin = computed(() => Boolean(auth.user.value?.is_superuser))
const navByWorkspace: Record<string, NavItem[]> = {
  MY: [
    { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue' },
    { label: 'Attendance', icon: 'i-lucide-calendar-check-2', to: '/attendance', iconTone: 'people-icon--blue' },
    { label: 'Leave', icon: 'i-lucide-calendar-days', to: '/leaves', iconTone: 'people-icon--forest' },
    { label: 'Work arrangements', icon: 'i-lucide-briefcase-business', to: '/work-arrangements', iconTone: 'people-icon--peach' },
    { label: 'Overtime', icon: 'i-lucide-timer', to: '/overtime', iconTone: 'people-icon--yellow' },
    { label: 'Shifts', icon: 'i-lucide-clock-3', to: '/shifts', iconTone: 'people-icon--blue' },
    { label: 'Holidays', icon: 'i-lucide-calendar-heart', to: '/holidays', iconTone: 'people-icon--forest' }
  ],
  TEAM: [
    { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue' },
    { label: 'Employees', icon: 'i-lucide-users-round', to: '/employees', iconTone: 'people-icon--mint', permissions: ['employee.view'] },
    { label: 'Attendance', icon: 'i-lucide-calendar-check-2', to: '/attendance', iconTone: 'people-icon--blue', permissions: ['attendance.view_department'] },
    { label: 'Leave approvals', icon: 'i-lucide-calendar-days', to: '/leaves', iconTone: 'people-icon--forest', permissions: ['leave.approve'] },
    { label: 'Work arrangements', icon: 'i-lucide-briefcase-business', to: '/work-arrangements', iconTone: 'people-icon--peach', permissions: ['work_arrangement.approve'] },
    { label: 'Overtime', icon: 'i-lucide-timer', to: '/overtime', iconTone: 'people-icon--yellow', permissions: ['overtime.view_department'] },
    { label: 'Approvals', icon: 'i-lucide-clipboard-check', to: '/approvals', iconTone: 'people-icon--rose', permissions: ['leave.approve', 'work_arrangement.approve', 'overtime.approve'] },
    { label: 'Shifts', icon: 'i-lucide-clock-3', to: '/shifts', iconTone: 'people-icon--blue', permissions: ['shift.view_self'] },
    { label: 'Reports', icon: 'i-lucide-chart-no-axes-combined', to: '/reports', iconTone: 'people-icon--yellow', permissions: ['reports.attendance', 'reports.leave'] }
  ],
  HR: [
    { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue' },
    { label: 'Employees', icon: 'i-lucide-users-round', to: '/employees', iconTone: 'people-icon--mint', permissions: ['employee.view'] },
    { label: 'Attendance', icon: 'i-lucide-calendar-check-2', to: '/attendance', iconTone: 'people-icon--blue', permissions: ['attendance.view', 'attendance.view_unit', 'attendance.process'] },
    { label: 'Leave management', icon: 'i-lucide-calendar-days', to: '/leaves', iconTone: 'people-icon--forest', permissions: ['leave.manage', 'leave.approve'] },
    { label: 'Work arrangements', icon: 'i-lucide-briefcase-business', to: '/work-arrangements', iconTone: 'people-icon--peach', permissions: ['work_arrangement.manage', 'work_arrangement.approve'] },
    { label: 'Overtime', icon: 'i-lucide-timer', to: '/overtime', iconTone: 'people-icon--yellow', permissions: ['overtime.view_department', 'overtime.approve'] },
    { label: 'Approvals', icon: 'i-lucide-clipboard-check', to: '/approvals', iconTone: 'people-icon--rose', permissions: ['leave.approve', 'work_arrangement.approve', 'overtime.approve'] },
    { label: 'Shifts', icon: 'i-lucide-clock-3', to: '/shifts', iconTone: 'people-icon--blue', permissions: ['shift.assign', 'shift.update'] },
    { label: 'Holidays', icon: 'i-lucide-calendar-heart', to: '/holidays', iconTone: 'people-icon--forest' },
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
const accountItems: NavItem[] = [
  { label: 'Profile', icon: 'i-lucide-user-round', to: '/profile' },
  { label: 'Settings', icon: 'i-lucide-settings', to: '/settings' },
  { label: 'Notifications', icon: 'i-lucide-bell', to: '/notifications' }
]
const globalSearchItems = computed(() => {
  const items = [...visibleItems.value, ...accountItems]
    .filter(item => workspace.canVisit(item.to))
    .map(item => item.to === '/settings' && isTechnicalAdmin.value ? { ...item, label: 'System administration' } : item)
  return Array.from(new Map(items.map(item => [item.to, item])).values())
})
const globalSearchResults = computed(() => {
  const query = globalSearchQuery.value.trim().toLocaleLowerCase()
  if (!query) return globalSearchItems.value
  return globalSearchItems.value.filter(item => item.label.toLocaleLowerCase().includes(query))
})
const mobileDestinations = computed(() => [...visibleItems.value, ...accountItems].map(item => item.to === '/settings' && isTechnicalAdmin.value
  ? { ...item, label: 'System administration', icon: 'i-lucide-shield-check' }
  : item))
// Home, Workspace and More occupy three of the five bar slots; the promoted role
// destinations take the rest. Everything else stays in the More drawer, so a
// page is never listed in both places.
const mobileTabs = computed(() => mobileTabPaths(currentWorkspace.value, availableWorkspaces.value.length > 1)
  .map(path => mobileDestinations.value.find(item => item.to === path))
  .filter((item): item is NavItem => Boolean(item && workspace.canVisit(item.to))))
const mobileTabSet = computed(() => new Set(mobileTabs.value.map(item => item.to)))
const mobileSheetItems = computed(() => {
  const seen = new Set<string>()
  return [...visibleItems.value, ...accountItems]
    .filter(item => item.to !== '/' && !mobileTabSet.value.has(item.to))
    .filter((item) => {
      if (seen.has(item.to)) return false
      seen.add(item.to)
      return true
    })
})
function openMobileGroup(label: string) {
  mobileGroup.value = label
  mobileOpen.value = true
}
function openGlobalSearch() {
  globalSearchQuery.value = ''
  globalSearchOpen.value = true
}
async function visitSearchResult(item: NavItem) {
  globalSearchOpen.value = false
  globalSearchQuery.value = ''
  await navigateTo(workspace.link(item.to))
}
async function changeWorkspace(event: Event) {
  const next = (event.target as HTMLSelectElement).value as Workspace
  await workspace.select(next)
}
watch(() => route.fullPath, () => {
  // Navigating should always collapse the mobile drawer.
  mobileOpen.value = false
  globalSearchOpen.value = false
})
onMounted(() => {
  const desktop = window.matchMedia('(min-width: 1024px)')
  const closeOnDesktop = () => {
    if (desktop.matches) mobileOpen.value = false
  }
  const openSearchShortcut = (event: KeyboardEvent) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'k') {
      event.preventDefault()
      openGlobalSearch()
    }
  }
  desktop.addEventListener('change', closeOnDesktop)
  window.addEventListener('keydown', openSearchShortcut)
  onBeforeUnmount(() => {
    desktop.removeEventListener('change', closeOnDesktop)
    window.removeEventListener('keydown', openSearchShortcut)
  })
})
</script>

<template>
  <div
    class="platform-shell"
    :class="{ 'platform-shell--collapsed': sidebarCollapsed }"
  >
    <a
      href="#platform-content"
      class="platform-skip-link"
    >Skip to content</a>
    <aside
      class="platform-sidebar"
      aria-label="Workspace sidebar"
    >
      <div class="platform-sidebar-heading">
        <NuxtLink
          :to="workspace.link('/')"
          class="platform-brand-link"
          aria-label="People by Datlabs — dashboard"
        >
          <BrandMark />
        </NuxtLink>
      </div>
      <div
        v-if="availableWorkspaces.length > 1"
        class="platform-workspace"
      >
        <UDropdownMenu
          v-if="sidebarCollapsed"
          :items="collapsedWorkspaceItems"
          :content="{ side: 'right', align: 'start' }"
        >
          <UButton
            :icon="workspaceDefinition.icon"
            color="neutral"
            variant="ghost"
            class="platform-icon-button"
            :aria-label="`Switch workspace: ${workspaceDefinition.label}`"
            :title="workspaceDefinition.label"
          />
        </UDropdownMenu>
        <template v-else>
          <label
            for="workspace-switcher"
            class="platform-workspace-label"
          >Workspace</label>
          <div class="platform-workspace-select">
            <select
              id="workspace-switcher"
              :value="currentWorkspace"
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
              class="size-4"
            />
          </div>
        </template>
      </div>
      <nav
        id="platform-primary-nav"
        class="platform-nav"
        aria-label="Primary navigation"
      >
        <section
          v-for="section in navSections"
          :key="section.label"
          :aria-label="`${section.label} navigation`"
          class="platform-nav-group"
        >
          <h2>{{ section.label }}</h2>
          <NuxtLink
            v-for="item in section.items"
            :key="item.to"
            :to="workspace.link(item.to)"
            class="platform-nav-link"
            :aria-label="item.label"
            :title="sidebarCollapsed ? item.label : undefined"
            :aria-current="route.path === item.to || (item.to !== '/' && route.path.startsWith(`${item.to}/`)) ? 'page' : undefined"
          >
            <UIcon
              :name="item.icon"
              class="size-5 shrink-0"
            />
            <span class="platform-nav-label">{{ item.label }}</span>
          </NuxtLink>
        </section>
        <NuxtLink
          v-if="isTechnicalAdmin"
          to="/settings"
          class="platform-nav-link"
          aria-label="System administration"
          :title="sidebarCollapsed ? 'System administration' : undefined"
          :aria-current="route.path === '/settings' ? 'page' : undefined"
        >
          <UIcon
            name="i-lucide-shield-check"
            class="size-5 shrink-0"
          />
          <span class="platform-nav-label">System administration</span>
        </NuxtLink>
      </nav>
      <div class="platform-account">
        <div class="platform-account-actions">
          <UButton
            v-if="!isTechnicalAdmin"
            to="/settings"
            icon="i-lucide-settings"
            color="neutral"
            variant="ghost"
            class="platform-icon-button"
            aria-label="Security settings"
          />
          <UButton
            icon="i-lucide-log-out"
            color="neutral"
            variant="ghost"
            class="platform-sign-out text-[var(--people-forest-ink)] bg-[var(--people-forest)] hover:bg-[var(--people-surface)]"
            aria-label="Sign out"
            title="Sign out"
            :loading="signingOut"
            :disabled="signingOut"
            @click="signOut"
          >
            <span v-if="!sidebarCollapsed">Sign out</span>
          </UButton>
        </div>
      </div>
    </aside>
    <div class="platform-body">
      <header class="platform-header">
        <UButton
          :icon="sidebarCollapsed ? 'i-lucide-panel-left-open' : 'i-lucide-panel-left-close'"
          color="neutral"
          variant="ghost"
          class="platform-icon-button platform-sidebar-toggle"
          :aria-label="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          :aria-expanded="!sidebarCollapsed"
          aria-controls="platform-primary-nav"
          @click="sidebarCollapsed = !sidebarCollapsed"
        />

        <NuxtLink
          :to="workspace.link('/')"
          class="platform-mobile-brand"
          aria-label="People by Datlabs — dashboard"
        ><BrandMark /></NuxtLink>
        <div class="platform-header-actions">
          <UButton
            icon="i-lucide-search"
            color="neutral"
            variant="ghost"
            class="platform-search-trigger"
            aria-label="Search pages"
            title="Search pages (Ctrl+K)"
            @click="openGlobalSearch"
          >
            <span class="platform-search-label">Search pages</span><kbd class="platform-search-shortcut">⌘ / Ctrl K</kbd>
          </UButton>
          <UButton
            icon="i-lucide-bell"
            color="neutral"
            variant="ghost"
            to="/notifications"
            class="platform-icon-button"
            aria-label="Notifications"
            :aria-current="route.path === '/notifications' ? 'page' : undefined"
          />
          <ClientOnly>
            <UColorModeButton class="platform-icon-button" />
            <template #fallback>
              <span
                class="platform-icon-button"
                aria-hidden="true"
              />
            </template>
          </ClientOnly>
          <NuxtLink
            to="/profile"
            class="platform-profile platform-header-profile"
            :aria-label="`Profile: ${auth.displayName.value}`"
            :title="auth.displayName.value"
          >
            <UAvatar
              :text="auth.initials.value"
              size="md"
            />
            <span class="platform-profile-copy">
              <span class="platform-profile-name">{{ auth.displayName.value }}</span>
            </span>
          </NuxtLink>
        </div>
      </header>
      <main
        id="platform-content"
        class="platform-content"
        tabindex="-1"
      >
        <slot />
      </main>
    </div>
    <UModal
      v-model:open="globalSearchOpen"
      title="Search People"
      description="Open a page available in your current workspace."
    >
      <template #body>
        <section class="platform-search">
          <UInput
            v-model="globalSearchQuery"
            icon="i-lucide-search"
            placeholder="Search pages"
            autocomplete="off"
            autofocus
            size="lg"
            class="w-full"
            @keydown.enter="globalSearchResults[0] && visitSearchResult(globalSearchResults[0])"
          />
          <p class="mt-3 text-xs text-muted">
            Searching {{ workspaceDefinition.label }} · Press Enter to open the first result
          </p>
          <div
            v-if="globalSearchResults.length"
            class="mt-4 grid max-h-80 gap-1 overflow-y-auto"
          >
            <button
              v-for="item in globalSearchResults"
              :key="item.to"
              type="button"
              class="flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-left text-sm font-medium transition-colors hover:bg-muted/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              @click="visitSearchResult(item)"
            >
              <UIcon
                :name="item.icon"
                class="size-5 shrink-0 text-muted"
              />
              <span class="min-w-0 flex-1 truncate">{{ item.label }}</span>
              <UIcon
                name="i-lucide-arrow-right"
                class="size-4 text-muted"
              />
            </button>
          </div>
          <div
            v-else
            class="mt-4 rounded-xl border border-dashed border-[var(--people-border)] px-4 py-8 text-center"
            role="status"
          >
            <p class="font-semibold">
              No matching pages
            </p>
            <p class="mt-1 text-sm text-muted">
              Try another page name.
            </p>
          </div>
        </section>
      </template>
    </UModal>
    <nav
      class="platform-mobile-nav"
      aria-label="Mobile navigation"
    >
      <div class="mx-auto flex max-w-lg items-center justify-around gap-1">
        <UButton
          :to="workspace.link('/')"
          icon="i-lucide-house"
          variant="ghost"
          color="neutral"
          class="min-h-12 flex-1 flex-col text-xs"
          aria-label="Home"
          :aria-current="route.path === '/' ? 'page' : undefined"
        >
          Home
        </UButton>
        <UButton
          v-if="availableWorkspaces.length > 1"
          icon="i-lucide-layout-grid"
          variant="ghost"
          color="neutral"
          class="min-h-12 flex-1 flex-col text-xs"
          :aria-label="`Workspace: ${workspaceDefinition.label}`"
          aria-haspopup="dialog"
          :aria-expanded="mobileOpen && mobileGroup === 'Workspace'"
          :data-selected="mobileOpen && mobileGroup === 'Workspace'"
          @click="openMobileGroup('Workspace')"
        >
          Workspace
        </UButton>
        <UButton
          v-for="item in mobileTabs"
          :key="item.to"
          :to="workspace.link(item.to)"
          :icon="item.icon"
          :aria-current="route.path === item.to || route.path.startsWith(`${item.to}/`) ? 'page' : undefined"
          variant="ghost"
          color="neutral"
          class="min-h-12 flex-1 flex-col text-xs leading-tight"
        >
          {{ item.label }}
        </UButton>
        <UButton
          icon="i-lucide-menu"
          color="neutral"
          variant="ghost"
          size="sm"
          class="min-h-12 min-w-0 flex-1 flex-col gap-0.5 px-1 py-2 text-xs"
          aria-label="More navigation"
          aria-haspopup="dialog"
          :aria-expanded="mobileOpen && mobileGroup === 'More'"
          :data-selected="(mobileOpen && mobileGroup === 'More') || mobileSheetItems.some(item => route.path === item.to || route.path.startsWith(`${item.to}/`))"
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
      :ui="{ content: 'max-h-[80dvh]', container: 'min-h-0', body: 'overflow-y-auto', footer: 'shrink-0 border-t border-[var(--people-border)] pb-[max(16px,env(safe-area-inset-bottom))]' }"
    >
      <template #body>
        <div
          v-if="mobileGroup === 'Workspace'"
          class="space-y-3"
        >
          <UButton
            v-for="item in availableWorkspaces"
            :key="item"
            :icon="WORKSPACES.find(definition => definition.key === item)?.icon"
            :variant="item === currentWorkspace ? 'soft' : 'ghost'"
            color="neutral"
            block
            class="min-h-12 justify-start"
            :aria-pressed="item === currentWorkspace"
            @click="workspace.select(item, '/'); mobileOpen = false"
          >
            {{ WORKSPACES.find(definition => definition.key === item)?.label }}
            <UIcon
              v-if="item === currentWorkspace"
              name="i-lucide-check"
            />
          </UButton>
        </div>
        <div
          v-else
          class="platform-mobile-links"
        >
          <NuxtLink
            v-for="item in mobileSheetItems"
            :key="item.to"
            :to="workspace.link(item.to)"
            class="platform-nav-link"
            :aria-current="route.path === item.to ? 'page' : undefined"
            @click="mobileOpen = false"
          >
            <UIcon
              :name="item.icon"
              class="size-5 shrink-0"
            />
            {{ item.label }}
          </NuxtLink>
        </div>
        <p
          v-if="mobileGroup !== 'Workspace' && !mobileSheetItems.length"
          class="py-6 text-sm text-muted"
        >
          No pages are available in this section.
        </p>
      </template>
      <template
        v-if="mobileGroup === 'More'"
        #footer
      >
        <UButton
          class="platform-mobile-sign-out text-[var(--people-forest-ink)] bg-[var(--people-forest)] hover:bg-[var(--people-surface)]"
          icon="i-lucide-log-out"
          color="neutral"
          variant="soft"
          :loading="signingOut"
          :disabled="signingOut"
          @click="signOut"
        >
          Sign out
        </UButton>
      </template>
    </UDrawer>
  </div>
</template>
