<script setup lang="ts">
/**
 * Application shell: sidebar navigation, top bar and content slot.
 *
 * Nav visibility is a single permission gate: an item is shown when the user
 * holds at least one of its permission codes (items without a list are
 * self-service and visible to everyone). Technical admins (superuser) skip the
 * business nav entirely and get a dedicated "System administration" link
 * instead.
 *
 * The gate is presentation only — every endpoint re-checks permission and row
 * scope, so a hidden link is convenience, never security.
 */
interface NavItem { label: string, icon: string, to: string, iconTone?: string, permissions?: string[] }
const route = useRoute()
const auth = useAuth()
const mobileOpen = ref(false)
const navItems: NavItem[] = [
  { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/', iconTone: 'people-icon--blue' },
  { label: 'Employees', icon: 'i-lucide-users-round', to: '/employees', iconTone: 'people-icon--mint', permissions: ['employee.view'] },
  { label: 'Attendance', icon: 'i-lucide-calendar-check-2', to: '/attendance', iconTone: 'people-icon--blue' },
  { label: 'Leave', icon: 'i-lucide-calendar-days', to: '/leaves', iconTone: 'people-icon--lavender' },
  { label: 'Work arrangements', icon: 'i-lucide-briefcase-business', to: '/work-arrangements', iconTone: 'people-icon--peach' },
  { label: 'Overtime', icon: 'i-lucide-timer', to: '/overtime', iconTone: 'people-icon--yellow' },
  { label: 'Approvals', icon: 'i-lucide-clipboard-check', to: '/approvals', iconTone: 'people-icon--rose', permissions: ['leave.approve', 'work_arrangement.approve'] },
  { label: 'Shifts', icon: 'i-lucide-clock-3', to: '/shifts', iconTone: 'people-icon--blue', permissions: ['shift.assign', 'shift.update'] },
  { label: 'Holidays', icon: 'i-lucide-calendar-heart', to: '/holidays', iconTone: 'people-icon--lavender' },
  { label: 'Organization', icon: 'i-lucide-building-2', to: '/organization', iconTone: 'people-icon--mint', permissions: ['designation.view'] },
  { label: 'Reports', icon: 'i-lucide-chart-no-axes-combined', to: '/reports', iconTone: 'people-icon--yellow', permissions: ['reports.attendance', 'reports.leave'] }
]
const isTechnicalAdmin = computed(() => Boolean(auth.user.value?.is_superuser))
// Technical admins manage master data in ERP, not here — so they only see
// the dashboard plus system administration. Everyone else sees every item their
// effective permissions unlock.
const visibleItems = computed(() => isTechnicalAdmin.value
  ? [{ label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/' }]
  : navItems.filter(item => !item.permissions || item.permissions.some(auth.hasPermission)))
const pageTitle = computed(() => route.path === '/settings'
  ? isTechnicalAdmin.value ? 'System administration' : 'Security settings'
  : navItems.find(item => item.to === route.path)?.label || 'People')
const mobileItems = computed(() => visibleItems.value.filter(item => item.to !== '/').slice(0, 4))
watch(() => route.fullPath, () => {
  // Navigating should always collapse the mobile drawer.
  mobileOpen.value = false
})
</script>

<template>
  <div class="min-h-dvh bg-[var(--people-canvas)]">
    <button
      v-if="mobileOpen"
      type="button"
      class="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-[2px] lg:hidden"
      aria-label="Close navigation"
      @click="mobileOpen = false"
    />
    <aside
      class="fixed inset-y-0 left-0 z-50 flex w-[17rem] flex-col border-r border-[var(--people-border)] bg-[var(--people-surface)] px-4 py-5 transition-transform lg:translate-x-0"
      :class="mobileOpen ? 'translate-x-0' : '-translate-x-full'"
    >
      <div class="flex items-center justify-between px-2">
        <BrandMark />
        <UButton
          class="lg:hidden"
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          aria-label="Close menu"
          @click="mobileOpen = false"
        />
      </div>
      <nav
        class="mt-9 flex-1 space-y-1"
        aria-label="Primary navigation"
      >
        <NuxtLink
          v-for="item in visibleItems"
          :key="item.to"
          :to="item.to"
          class="flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors"
          :class="route.path === item.to || (item.to !== '/' && route.path.startsWith(item.to)) ? 'bg-[var(--people-lavender)] text-primary-700 dark:text-primary-300' : 'text-muted hover:bg-muted/10 hover:text-highlighted'"
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
        <UButton
          class="lg:hidden"
          icon="i-lucide-user-round"
          color="neutral"
          variant="ghost"
          to="/profile"
          aria-label="Open profile"
        />
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
          v-for="item in mobileItems"
          :key="item.to"
          :to="item.to"
          :icon="item.icon"
          :color="route.path === item.to || (item.to !== '/' && route.path.startsWith(item.to)) ? 'primary' : 'neutral'"
          :variant="route.path === item.to || (item.to !== '/' && route.path.startsWith(item.to)) ? 'soft' : 'ghost'"
          size="sm"
          class="min-w-0 flex-1 flex-col gap-0.5 px-1 py-2 text-[10px]"
          :aria-label="item.label"
        >
          {{ item.label }}
        </UButton>
        <UButton
          to="/profile"
          icon="i-lucide-user-round"
          color="neutral"
          :variant="route.path === '/profile' ? 'soft' : 'ghost'"
          size="sm"
          class="min-w-0 flex-1 flex-col gap-0.5 px-1 py-2 text-[10px]"
          aria-label="Profile"
        >
          Profile
        </UButton>
      </div>
    </nav>
  </div>
</template>
