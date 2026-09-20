<script setup lang="ts">
interface NavItem { label: string, icon: string, to: string, permissions?: string[] }
const route = useRoute()
const auth = useAuth()
const mobileOpen = ref(false)
const navItems: NavItem[] = [
  { label: 'Dashboard', icon: 'i-lucide-layout-dashboard', to: '/' },
  { label: 'Employees', icon: 'i-lucide-users-round', to: '/employees', permissions: ['employee.view'] },
  { label: 'Attendance', icon: 'i-lucide-calendar-check-2', to: '/attendance' },
  { label: 'Leave', icon: 'i-lucide-calendar-days', to: '/leaves' },
  { label: 'Work arrangements', icon: 'i-lucide-briefcase-business', to: '/work-arrangements' },
  { label: 'Overtime', icon: 'i-lucide-timer', to: '/overtime' },
  { label: 'Approvals', icon: 'i-lucide-clipboard-check', to: '/approvals', permissions: ['leave.approve', 'attendance.approve_correction', 'overtime.approve', 'work_arrangement.approve'] },
  { label: 'Shifts', icon: 'i-lucide-clock-3', to: '/shifts', permissions: ['shift.view_self', 'shift.assign', 'shift.update'] },
  { label: 'Holidays', icon: 'i-lucide-calendar-heart', to: '/holidays' },
  { label: 'Organization', icon: 'i-lucide-building-2', to: '/organization', permissions: ['system.configure', 'designation.view', 'employee.view'] },
  { label: 'Reports', icon: 'i-lucide-chart-no-axes-combined', to: '/reports', permissions: ['reports.attendance', 'reports.leave'] }
]
const visibleItems = computed(() => navItems.filter(item => !item.permissions || item.permissions.some(auth.hasPermission)))
const pageTitle = computed(() => navItems.find(item => item.to === route.path)?.label || 'People')
watch(() => route.fullPath, () => {
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
          <UIcon
            :name="item.icon"
            class="size-[18px] shrink-0"
          />{{ item.label }}
        </NuxtLink>
      </nav>
      <div class="border-t border-[var(--people-border)] pt-4">
        <div class="flex items-center gap-3 rounded-xl px-2 py-2">
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
        </div>
      </div>
    </aside>
    <div class="lg:pl-[17rem]">
      <header class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-[var(--people-border)] bg-[var(--people-surface)]/90 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
        <UButton
          class="lg:hidden"
          icon="i-lucide-menu"
          color="neutral"
          variant="ghost"
          aria-label="Open navigation"
          @click="mobileOpen = true"
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
      <main class="mx-auto w-full max-w-[96rem] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <slot />
      </main>
    </div>
  </div>
</template>
