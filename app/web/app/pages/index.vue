<script setup lang="ts">
import type { DashboardMetrics, EmployeeDashboardShift } from '#shared/types/dashboard'

useSeoMeta({ title: 'Dashboard' })
const auth = useAuth()
const api = useHrmsApi()
const workspace = useWorkspace()
const isTechnicalAdmin = computed(() => Boolean(auth.user.value?.is_superuser))
const isExecutiveWorkspace = computed(() => workspace.current.value === 'EXECUTIVE')
const scopeType = computed(() => auth.scopeType.value)
const hasTeamScope = computed(() => workspace.current.value === 'TEAM' || workspace.current.value === 'HR')
const canReviewApprovals = computed(() => ['leave.approve', 'work_arrangement.approve'].some(auth.hasPermission))
const teamLabel = computed(() => scopeType.value === 'ORGANIZATION' ? 'Organization members' : scopeType.value === 'UNIT' ? 'Unit members' : scopeType.value === 'DEPARTMENT' ? 'Department members' : 'Employees')
const dashboardTitle = computed(() => isTechnicalAdmin.value ? 'Technical administration' : workspace.current.value === 'EXECUTIVE' ? 'Organization performance at a glance.' : workspace.current.value === 'HR' ? 'People operations at a glance.' : workspace.current.value === 'TEAM' ? 'Your team at a glance.' : 'Here’s your workday at a glance.')
const dashboardSubtitle = computed(() => isTechnicalAdmin.value ? 'System access, ERP structure and technical account settings.' : workspace.current.value === 'EXECUTIVE' ? 'Monitor company-wide attendance, workforce exceptions, leave and overtime.' : workspace.current.value === 'HR' ? `Manage people operations across your ${scopeType.value === 'ORGANIZATION' ? 'organization' : 'unit'} scope.` : workspace.current.value === 'TEAM' ? 'Review your department attendance, leave and approval workload.' : 'Review your attendance, leave balance and work schedule.')
const greeting = computed(() => {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
})
const { data: response, pending, error, refresh } = useLazyAsyncData('dashboard-metrics', () => api.request<DashboardMetrics>('dashboard/metrics'), { immediate: !isTechnicalAdmin.value && !isExecutiveWorkspace.value })
watch(() => workspace.current.value, () => {
  if (!isTechnicalAdmin.value && !isExecutiveWorkspace.value) void refresh()
})
const lastData = shallowRef<DashboardMetrics>()
watch(response, (value) => {
  if (value) lastData.value = value
}, { immediate: true })
const data = computed(() => response.value || lastData.value)
const { data: technicalResponse, pending: technicalPending, error: technicalError, refresh: refreshTechnical } = useLazyAsyncData('technical-admin-metrics', () => api.request<{ users: number, employees: number, units: number, departments: number, designations: number }>('dashboard/technical-metrics'), { immediate: isTechnicalAdmin.value })
const lastTechnical = shallowRef<typeof technicalResponse.value>()
watch(technicalResponse, (value) => {
  if (value) lastTechnical.value = value
}, { immediate: true })
const technicalMetrics = computed(() => technicalResponse.value || lastTechnical.value)
const technicalStats = computed(() => [
  { label: 'Users', value: technicalMetrics.value?.users ?? 0, icon: 'i-lucide-users-round' },
  { label: 'Employees', value: technicalMetrics.value?.employees ?? 0, icon: 'i-lucide-user-round' },
  { label: 'Units', value: technicalMetrics.value?.units ?? 0, icon: 'i-lucide-building-2' },
  { label: 'Departments', value: technicalMetrics.value?.departments ?? 0, icon: 'i-lucide-network' },
  { label: 'Designations', value: technicalMetrics.value?.designations ?? 0, icon: 'i-lucide-badge' }
])
const stats = computed(() => hasTeamScope.value
  ? [
      { label: teamLabel.value, value: data.value?.unitMetrics.totalHeadcount ?? 0, icon: 'i-lucide-users-round' },
      { label: 'Present today', value: data.value?.unitMetrics.presentCount ?? 0, icon: 'i-lucide-circle-check-big' },
      { label: 'On leave', value: data.value?.unitMetrics.leaveCount ?? 0, icon: 'i-lucide-calendar-heart' },
      { label: 'Needs attention', value: (data.value?.unitMetrics.pendingLeaves ?? 0) + (data.value?.unitMetrics.pendingCorrections ?? 0), icon: 'i-lucide-inbox' }
    ]
  : [
      { label: 'Present this month', value: data.value?.employeeMetrics.monthlyPresent ?? 0, icon: 'i-lucide-circle-check-big' },
      { label: 'Absent this month', value: data.value?.employeeMetrics.monthlyAbsent ?? 0, icon: 'i-lucide-calendar-x-2' },
      { label: 'Leave days', value: data.value?.employeeMetrics.monthlyLeave ?? 0, icon: 'i-lucide-calendar-heart' },
      { label: 'Overtime', value: `${data.value?.employeeMetrics.overtimeHours ?? 0}h`, icon: 'i-lucide-timer' }
    ])

const formatShiftTime = (value?: string) => value
  ? new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true }).format(new Date(value))
  : '—'

const formatShiftDate = (shift?: EmployeeDashboardShift | null) => {
  if (!shift) return 'No upcoming assignment'
  return new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(`${shift.shiftDate}T00:00:00`))
}

const shiftTimeRange = (shift?: EmployeeDashboardShift | null) => shift
  ? `${formatShiftTime(shift.startsAt)} – ${formatShiftTime(shift.endsAt)}`
  : 'Not assigned'
</script>

<template>
  <div class="people-page dashboard-page">
    <header class="dashboard-heading">
      <div>
        <h1>{{ dashboardTitle }}</h1>
        <p>{{ dashboardSubtitle }}</p>
      </div>
      <div class="dashboard-meta">
        <span>{{ greeting }}, {{ auth.user.value?.first_name || auth.user.value?.username }}</span>
        <time>{{ new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date()) }}</time>
      </div>
    </header>

    <template v-if="isTechnicalAdmin">
      <UAlert
        color="info"
        variant="soft"
        icon="i-lucide-shield-check"
        title="Technical administration workspace"
        description="Manage system access, ERP integrations, synchronization health and technical account settings. This account is not an employee and does not have attendance, leave or approval records."
        :actions="[{ label: 'Open system administration', to: '/settings' }]"
      />
      <UAlert
        v-if="technicalError"
        color="error"
        title="Technical metrics could not be loaded"
        :actions="[{ label: 'Retry', onClick: () => refreshTechnical() }]"
      />
      <p
        v-if="technicalPending"
        class="dashboard-sync"
        role="status"
      >
        {{ technicalMetrics ? 'Updating technical metrics…' : 'Loading technical metrics…' }}
      </p>
      <DashboardSummary
        :items="technicalStats"
        variant="technical"
        :pending="technicalPending"
        :unavailable="!technicalMetrics"
      />
      <div class="dashboard-columns">
        <section class="dashboard-panel">
          <h2>Technical administration</h2>
          <p class="dashboard-description">
            Monitor the structure managed by ERP and maintain this technical account.
          </p>
          <div class="dashboard-panel-actions">
            <UButton
              to="/settings"
              icon="i-lucide-shield-check"
            >
              Account settings
            </UButton>
          </div>
        </section>
        <section class="dashboard-panel">
          <h2>ERP ownership</h2>
          <p class="dashboard-description">
            Employees, users, units, departments and designations are synchronized from ERP.
          </p>
          <div class="dashboard-panel-actions">
            <UButton
              to="/organization"
              color="neutral"
              variant="outline"
              icon="i-lucide-eye"
            >
              View organization
            </UButton>
          </div>
        </section>
      </div>
    </template>

    <DashboardOwnerDashboard v-else-if="isExecutiveWorkspace" />

    <template v-else>
      <UAlert
        v-if="error"
        color="error"
        title="Your dashboard could not be refreshed"
        description="Please try again. Any displayed results are from the last successful update."
        :actions="[{ label: 'Refresh dashboard', onClick: () => refresh() }]"
      />
      <p
        v-if="pending"
        class="dashboard-sync"
        role="status"
      >
        {{ data ? 'Updating dashboard…' : 'Loading dashboard…' }}
      </p>
      <DashboardSummary
        :items="stats"
        :pending="pending"
        :unavailable="!data"
      />
      <div class="dashboard-columns">
        <section
          v-if="!hasTeamScope"
          class="dashboard-panel"
          :aria-busy="pending"
        >
          <h2>Your shifts</h2>
          <p class="dashboard-description">
            Your assigned shift and next scheduled workday
          </p>
          <USkeleton
            v-if="pending && !data"
            class="mt-6 h-24 w-full"
          />
          <dl
            v-else-if="data"
            class="dashboard-details"
          >
            <div><dt>Assigned shift</dt><dd>{{ data.employeeMetrics.currentShift?.name || 'Not assigned' }}</dd><small>{{ shiftTimeRange(data.employeeMetrics.currentShift) }}</small></div>
            <div><dt>Upcoming shift</dt><dd>{{ data.employeeMetrics.upcomingShift?.name || 'No upcoming shift' }}</dd><small>{{ data.employeeMetrics.upcomingShift ? `${formatShiftDate(data.employeeMetrics.upcomingShift)} · ${shiftTimeRange(data.employeeMetrics.upcomingShift)}` : 'No upcoming assignment' }}</small></div>
          </dl>
          <p
            v-else
            class="dashboard-description"
          >
            Shift information is unavailable.
          </p>
        </section>
        <section
          v-if="!hasTeamScope"
          class="dashboard-panel"
          :aria-busy="pending"
        >
          <div class="dashboard-section-heading">
            <div>
              <h2>Today</h2><p class="dashboard-description">
                Your ERP-synced attendance
              </p>
            </div><UBadge
              v-if="data"
              :label="data.employeeMetrics.todayStatus || 'Not marked'"
              color="neutral"
              variant="soft"
            />
          </div>
          <USkeleton
            v-if="pending && !data"
            class="mt-6 h-24 w-full"
          />
          <dl
            v-else-if="data"
            class="dashboard-details"
          >
            <div><dt>Punch in</dt><dd>{{ data.employeeMetrics.punchIn || '—' }}</dd></div><div><dt>Punch out</dt><dd>{{ data.employeeMetrics.punchOut || '—' }}</dd></div>
          </dl>
          <p
            v-else
            class="dashboard-description"
          >
            Attendance information is unavailable.
          </p>
          <div class="dashboard-panel-actions">
            <UButton
              to="/attendance"
              color="neutral"
              variant="outline"
              icon="i-lucide-calendar-days"
            >
              View attendance
            </UButton>
          </div>
        </section>
        <section
          v-if="hasTeamScope && canReviewApprovals"
          class="dashboard-panel"
          :aria-busy="pending"
        >
          <div class="dashboard-section-heading">
            <div>
              <h2>Pending approvals</h2><p class="dashboard-description">
                Requests waiting for review
              </p>
            </div><UButton
              to="/approvals"
              color="neutral"
              variant="ghost"
              trailing-icon="i-lucide-arrow-right"
            >
              View all
            </UButton>
          </div>
          <USkeleton
            v-if="pending && !data"
            class="mt-6 h-36 w-full"
          />
          <div
            v-else-if="data?.pendingApprovals.length"
            class="dashboard-approval-list"
          >
            <div
              v-for="item in data.pendingApprovals.slice(0, 4)"
              :key="item.id"
              class="dashboard-approval-row"
            >
              <div><p>{{ item.employeeName || 'Employee request' }}</p><small>{{ item.detail || item.type }}</small></div><time>{{ item.timeAgo }}</time>
            </div>
          </div>
          <div
            v-else-if="data"
            class="dashboard-empty"
          >
            <p>All caught up</p><small>There are no requests waiting for you.</small>
          </div>
          <p
            v-else
            class="dashboard-description"
          >
            Approval information is unavailable.
          </p>
        </section>
      </div>
    </template>
  </div>
</template>
