<script setup lang="ts">
import type { DashboardMetrics } from '#shared/types/dashboard'

useSeoMeta({ title: 'Dashboard' })
const auth = useAuth()
const api = useHrmsApi()
const isTechnicalAdmin = computed(() => Boolean(auth.user.value?.is_superuser))
const role = computed(() => auth.user.value?.role || 'EMPLOYEE')
const isManager = computed(() => role.value === 'DEPARTMENT_MANAGER' || role.value === 'HR_ADMIN')
const dashboardTitle = computed(() => role.value === 'HR_ADMIN' ? 'Unit operations at a glance.' : role.value === 'DEPARTMENT_MANAGER' ? 'Your department at a glance.' : 'Here’s your workday at a glance.')
const dashboardSubtitle = computed(() => role.value === 'HR_ADMIN' ? 'Monitor unit attendance and handle requests that need HR attention.' : role.value === 'DEPARTMENT_MANAGER' ? 'Review your department attendance, leave and approval workload.' : 'Review your attendance, leave balance and work schedule.')
const greeting = computed(() => {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
})
const { data, pending, error, refresh } = await useAsyncData('dashboard-metrics', () => api.request<DashboardMetrics>('dashboard/metrics'))
const { data: technicalMetrics } = await useAsyncData('technical-admin-metrics', () => api.request<{ users: number, employees: number, units: number, departments: number, designations: number }>('dashboard/technical-metrics'), { immediate: isTechnicalAdmin.value })
const stats = computed(() => isManager.value
  ? [
      { label: role.value === 'HR_ADMIN' ? 'Unit members' : 'Department members', value: data.value?.unitMetrics.totalHeadcount ?? 0, icon: 'i-lucide-users-round', tone: 'var(--people-blue)' },
      { label: 'Present today', value: data.value?.unitMetrics.presentCount ?? 0, icon: 'i-lucide-circle-check-big', tone: 'var(--people-mint)' },
      { label: 'On leave', value: data.value?.unitMetrics.leaveCount ?? 0, icon: 'i-lucide-calendar-heart', tone: 'var(--people-lavender)' },
      { label: 'Needs attention', value: (data.value?.unitMetrics.pendingLeaves ?? 0) + (data.value?.unitMetrics.pendingCorrections ?? 0), icon: 'i-lucide-inbox', tone: 'var(--people-peach)' }
    ]
  : [
      { label: 'Present this month', value: data.value?.employeeMetrics.monthlyPresent ?? 0, icon: 'i-lucide-circle-check-big', tone: 'var(--people-mint)' },
      { label: 'Absent this month', value: data.value?.employeeMetrics.monthlyAbsent ?? 0, icon: 'i-lucide-calendar-x-2', tone: 'var(--people-peach)' },
      { label: 'Leave days', value: data.value?.employeeMetrics.monthlyLeave ?? 0, icon: 'i-lucide-calendar-heart', tone: 'var(--people-lavender)' },
      { label: 'Overtime', value: `${data.value?.employeeMetrics.overtimeHours ?? 0}h`, icon: 'i-lucide-timer', tone: 'var(--people-blue)' }
    ])
</script>

<template>
  <div>
    <UAlert
      v-if="auth.user.value?.is_superuser"
      color="info"
      variant="soft"
      icon="i-lucide-shield-check"
      title="Technical administration workspace"
      description="Manage system access, ERP integrations, synchronization health and technical account settings. This account is not an employee and does not have attendance, leave or approval records."
      :actions="[{ label: 'Open system administration', to: '/settings' }]"
    />
    <!-- eslint-disable better-tailwindcss/no-unknown-classes -->
    <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p class="text-sm font-medium text-muted">
          {{ greeting }}, {{ auth.user.value?.first_name || auth.user.value?.username }}
        </p>
        <h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          {{ dashboardTitle }}
        </h2>
        <p class="mt-2 max-w-2xl text-sm text-muted">
          {{ dashboardSubtitle }}
        </p>
      </div>
      <p class="text-sm text-muted">
        {{ new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date()) }}
      </p>
    </div>

    <template v-if="isTechnicalAdmin">
      <div class="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <div
          v-for="item in [
            { label: 'Users', value: technicalMetrics?.users ?? 0, icon: 'i-lucide-users-round', tone: 'var(--people-blue)' },
            { label: 'Employees', value: technicalMetrics?.employees ?? 0, icon: 'i-lucide-user-round', tone: 'var(--people-mint)' },
            { label: 'Units', value: technicalMetrics?.units ?? 0, icon: 'i-lucide-building-2', tone: 'var(--people-lavender)' },
            { label: 'Departments', value: technicalMetrics?.departments ?? 0, icon: 'i-lucide-network', tone: 'var(--people-peach)' },
            { label: 'Designations', value: technicalMetrics?.designations ?? 0, icon: 'i-lucide-badge', tone: 'var(--people-yellow)' }
          ]"
          :key="item.label"
          class="people-card p-5"
        >
          <div class="flex items-start justify-between">
            <p class="text-sm font-medium text-muted">
              {{ item.label }}
            </p><span
              class="grid size-10 place-items-center rounded-xl"
              :style="{ background: item.tone }"
            ><UIcon
              :name="item.icon"
              class="size-5"
            /></span>
          </div>
          <p class="mt-4 text-3xl font-semibold tabular-nums">
            {{ item.value }}
          </p>
        </div>
      </div>
      <div class="mt-6 grid gap-6 lg:grid-cols-2">
        <section class="people-card p-5 sm:p-6">
          <div class="flex items-start gap-3">
            <span class="grid size-10 place-items-center rounded-xl bg-[var(--people-lavender)]"><UIcon
              name="i-lucide-settings-2"
              class="size-5"
            /></span><div>
              <h3 class="font-semibold">
                Technical administration
              </h3><p class="mt-1 text-sm text-muted">
                Monitor the structure managed by ERP and maintain this technical account.
              </p>
            </div>
          </div><UButton
            class="mt-5"
            to="/settings"
            icon="i-lucide-shield-check"
          >
            Account settings
          </UButton>
        </section>
        <section class="people-card p-5 sm:p-6">
          <div class="flex items-start gap-3">
            <span class="grid size-10 place-items-center rounded-xl bg-[var(--people-blue)]"><UIcon
              name="i-lucide-refresh-cw"
              class="size-5"
            /></span><div>
              <h3 class="font-semibold">
                ERP ownership
              </h3><p class="mt-1 text-sm text-muted">
                Employees, users, units, departments and designations are synchronized from ERP.
              </p>
            </div>
          </div><UButton
            class="mt-5"
            to="/organization"
            color="neutral"
            variant="soft"
            icon="i-lucide-eye"
          >
            View organization
          </UButton>
        </section>
      </div>
    </template>

    <template v-else>
      <UAlert
        v-if="error"
        class="mt-6"
        color="warning"
        variant="soft"
        icon="i-lucide-coffee"
        title="Your dashboard is taking a short break"
        description="We couldn’t refresh your latest People updates right now. Please try again in a moment."
        :actions="[{ label: 'Refresh dashboard', onClick: () => refresh() }]"
      />

      <div class="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="stat in stats"
          :key="stat.label"
          class="people-card p-5"
        >
          <div class="flex items-start justify-between">
            <p class="text-sm font-medium text-muted">
              {{ stat.label }}
            </p><span
              class="grid size-10 place-items-center rounded-xl"
              :style="{ background: stat.tone }"
            ><UIcon
              :name="stat.icon"
              class="size-5"
            /></span>
          </div>
          <USkeleton
            v-if="pending"
            class="mt-5 h-9 w-20"
          />
          <p
            v-else
            class="mt-4 text-3xl font-semibold tabular-nums"
          >
            {{ stat.value }}
          </p>
        </div>
      </div>

      <div class="mt-6 grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <UCard>
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-semibold">
                Today
              </h3><p class="mt-1 text-sm text-muted">
                Your ERP-synced attendance and schedule
              </p>
            </div>
            <UBadge
              :label="data?.employeeMetrics.todayStatus || 'Not marked'"
              color="neutral"
              variant="soft"
            />
          </div>
          <div class="mt-6 grid gap-3 sm:grid-cols-3">
            <div class="rounded-xl bg-muted/5 p-4">
              <p class="text-xs font-medium text-muted">
                Current shift
              </p><p class="mt-2 font-semibold">
                {{ data?.employeeMetrics.currentShift || 'Not assigned' }}
              </p>
            </div>
            <div class="rounded-xl bg-muted/5 p-4">
              <p class="text-xs font-medium text-muted">
                Punch in
              </p><p class="mt-2 font-semibold tabular-nums">
                {{ data?.employeeMetrics.punchIn || '—' }}
              </p>
            </div>
            <div class="rounded-xl bg-muted/5 p-4">
              <p class="text-xs font-medium text-muted">
                Punch out
              </p><p class="mt-2 font-semibold tabular-nums">
                {{ data?.employeeMetrics.punchOut || '—' }}
              </p>
            </div>
          </div>
          <div class="mt-6 flex flex-wrap gap-3">
            <UButton
              to="/attendance"
              color="neutral"
              variant="soft"
              icon="i-lucide-calendar-days"
            >
              View attendance
            </UButton>
          </div>
        </UCard>

        <UCard v-if="isManager">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-semibold">
                Pending approvals
              </h3><p class="mt-1 text-sm text-muted">
                Requests waiting for review
              </p>
            </div>
            <UButton
              to="/approvals"
              color="neutral"
              variant="ghost"
              trailing-icon="i-lucide-arrow-right"
            >
              View all
            </UButton>
          </div>
          <div
            v-if="data?.pendingApprovals.length"
            class="mt-5 space-y-3"
          >
            <div
              v-for="item in data.pendingApprovals.slice(0, 4)"
              :key="item.id"
              class="flex items-center gap-3 rounded-xl border border-[var(--people-border)] p-3"
            >
              <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-[var(--people-lavender)]"><UIcon
                name="i-lucide-clipboard-check"
                class="size-5"
              /></span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-semibold">
                  {{ item.employeeName || 'Employee request' }}
                </p><p class="truncate text-xs text-muted">
                  {{ item.detail || item.type }}
                </p>
              </div>
              <span class="text-xs text-muted">{{ item.timeAgo }}</span>
            </div>
          </div>
          <div
            v-else
            class="mt-8 flex flex-col items-center py-6 text-center"
          >
            <span class="grid size-12 place-items-center rounded-2xl bg-[var(--people-mint)]"><UIcon
              name="i-lucide-circle-check-big"
              class="size-6"
            /></span>
            <p class="mt-4 text-sm font-semibold">
              All caught up
            </p><p class="mt-1 text-xs text-muted">
              There are no requests waiting for you.
            </p>
          </div>
        </UCard>
      </div>
    </template>
  </div>
</template>
