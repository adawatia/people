<script setup lang="ts">
import type { Unit } from '#shared/types/organization'
import type { OwnerDashboard, OwnerExceptionResponse } from '#shared/types/dashboard'

const api = useHrmsApi()
const today = new Date().toISOString().slice(0, 10)
const rangeStart = new Date(Date.now() - 29 * 86_400_000).toISOString().slice(0, 10)
const fromDate = ref(rangeStart)
const toDate = ref(today)
const unitId = ref<number>(0)
const exceptionKind = ref<'absent' | 'late' | 'late_or_missed_punch' | 'missed_punch' | 'on_leave' | 'pending_request'>('absent')
const exceptionPage = ref(1)
const showExceptions = ref(false)

const { data: units } = await useAsyncData('owner-dashboard-units', () => api.request<Unit[]>('org/units'))
const dashboardKey = computed(() => `owner-dashboard-${fromDate.value}-${toDate.value}-${unitId.value}`)
const { data, pending, error, refresh } = await useAsyncData(
  dashboardKey,
  () => api.request<OwnerDashboard>('dashboard/owner', { query: { from_date: fromDate.value, to_date: toDate.value, unit_id: unitId.value || undefined } }),
  { watch: [fromDate, toDate, unitId] }
)
const { data: exceptions, pending: exceptionsPending, refresh: refreshExceptions } = await useAsyncData(
  'owner-dashboard-exceptions',
  () => api.request<OwnerExceptionResponse>('dashboard/owner/exceptions', { query: { kind: exceptionKind.value, target_date: toDate.value, unit_id: unitId.value || undefined, page: exceptionPage.value } }),
  { watch: [exceptionKind, exceptionPage, unitId, toDate], immediate: false }
)

const trendOption = computed<ECOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { bottom: 0 },
  grid: { left: 40, right: 16, top: 20, bottom: 52 },
  xAxis: { type: 'category', data: data.value?.trend.map(item => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' }).format(new Date(`${item.date}T00:00:00`))) || [] },
  yAxis: { type: 'value', minInterval: 1 },
  series: [
    { name: 'Present', type: 'bar', stack: 'attendance', data: data.value?.trend.map(item => item.present) || [], itemStyle: { color: '#34d399' } },
    { name: 'Absent', type: 'bar', stack: 'attendance', data: data.value?.trend.map(item => item.absent) || [], itemStyle: { color: '#fb7185' } },
    { name: 'On leave', type: 'bar', stack: 'attendance', data: data.value?.trend.map(item => item.on_leave) || [], itemStyle: { color: '#a78bfa' } },
    { name: 'Off / holiday', type: 'bar', stack: 'attendance', data: data.value?.trend.map(item => item.weekly_off_or_holiday) || [], itemStyle: { color: '#94a3b8' } }
  ]
}))

const metrics = computed(() => [
  { label: 'Active workforce', value: data.value?.summary.active_headcount ?? 0, icon: 'i-lucide-users-round', tone: 'var(--people-blue)' },
  { label: `Present on ${selectedDayLabel.value}`, value: data.value?.summary.present ?? 0, icon: 'i-lucide-circle-check-big', tone: 'var(--people-mint)' },
  { label: `Absent on ${selectedDayLabel.value}`, value: data.value?.summary.absent ?? 0, icon: 'i-lucide-calendar-x-2', tone: 'var(--people-peach)' },
  { label: 'On leave', value: data.value?.summary.on_leave ?? 0, icon: 'i-lucide-calendar-heart', tone: 'var(--people-lavender)' },
  { label: 'Attendance rate', value: `${data.value?.summary.attendance_rate ?? 0}%`, icon: 'i-lucide-chart-no-axes-combined', tone: 'var(--people-yellow)' },
  { label: 'Open exceptions', value: data.value?.summary.late_or_missed_punches ?? 0, icon: 'i-lucide-triangle-alert', tone: 'var(--people-peach)' }
])
const selectedDayLabel = computed(() => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' }).format(new Date(`${toDate.value}T00:00:00`)))

function openExceptions(kind: typeof exceptionKind.value) {
  exceptionPage.value = 1
  exceptionKind.value = kind
  showExceptions.value = true
  void refreshExceptions()
}
const formatHours = (minutes: number) => `${(minutes / 60).toFixed(1)}h`
</script>

<template>
  <section>
    <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">Organization operations</p>
        <h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Workforce health at a glance</h2>
        <p class="mt-2 text-sm text-muted">Company-wide attendance, exceptions, leave, and overtime from ERP-synced records.</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <UInput v-model="fromDate" type="date" aria-label="Analytics start date" />
        <UInput v-model="toDate" type="date" aria-label="Analytics end date" />
        <USelect v-model="unitId" :items="[{ label: 'All units', value: 0 }, ...(units || []).map(unit => ({ label: unit.name, value: unit.id }))]" class="min-w-44" />
        <UButton icon="i-lucide-refresh-cw" color="neutral" variant="soft" :loading="pending" @click="() => refresh()">Refresh</UButton>
      </div>
    </div>
    <p class="mt-3 text-xs text-muted">ERP attendance last synced: {{ data?.attendance_last_synced_at ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(data.attendance_last_synced_at)) : 'No sync timestamp available' }}</p>

    <UAlert v-if="error" class="mt-5" color="error" variant="soft" title="Organization analytics could not be loaded" description="Refresh the dashboard or verify the ERP synchronization status." />
    <div class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
      <div v-for="metric in metrics" :key="metric.label" class="people-card p-4">
        <div class="flex items-start justify-between gap-3"><p class="text-xs font-medium text-muted">{{ metric.label }}</p><span class="grid size-8 place-items-center rounded-lg" :style="{ background: metric.tone }"><UIcon :name="metric.icon" class="size-4" /></span></div>
        <p class="mt-3 text-2xl font-semibold tabular-nums">{{ metric.value }}</p>
      </div>
    </div>

    <div class="mt-6 grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
      <section class="people-card p-5"><h3 class="font-semibold">30-day attendance trend</h3><p class="mt-1 text-sm text-muted">Daily attendance composition; use the table below as an accessible text alternative.</p><ClientOnly><VChart class="mt-5 h-80 w-full" :option="trendOption" autoresize /><template #fallback><USkeleton class="mt-5 h-80 w-full" /></template></ClientOnly></section>
      <section class="people-card p-5"><h3 class="font-semibold">Needs attention</h3><p class="mt-1 text-sm text-muted">Open cohorts are safe to drill into.</p><div class="mt-5 space-y-3"><UButton block color="neutral" variant="soft" @click="openExceptions('absent')">{{ data?.summary.absent ?? 0 }} absent on {{ selectedDayLabel }}</UButton><UButton block color="neutral" variant="soft" @click="openExceptions('late_or_missed_punch')">{{ data?.summary.late_or_missed_punches ?? 0 }} late or missed punches</UButton><UButton block color="neutral" variant="soft" @click="openExceptions('on_leave')">{{ data?.summary.on_leave ?? 0 }} employees on leave</UButton><UButton block color="neutral" variant="soft" @click="openExceptions('pending_request')">{{ data?.summary.pending_requests ?? 0 }} pending requests</UButton></div><div class="mt-6 rounded-xl bg-muted/5 p-4"><p class="text-xs font-medium text-muted">Approved overtime in selected period</p><p class="mt-2 text-2xl font-semibold">{{ formatHours(data?.summary.approved_overtime_minutes ?? 0) }}</p></div></section>
    </div>

    <section class="people-card mt-6 overflow-hidden"><div class="border-b border-[var(--people-border)] p-5"><h3 class="font-semibold">{{ unitId ? 'Department performance' : 'Unit performance' }}</h3><p class="mt-1 text-sm text-muted">Select a unit above to compare its departments.</p></div><div class="overflow-x-auto"><table class="w-full min-w-[720px] text-left text-sm"><thead class="bg-muted/5 text-xs uppercase tracking-wide text-muted"><tr><th class="px-5 py-3">Group</th><th class="px-4 py-3">Headcount</th><th class="px-4 py-3">Present</th><th class="px-4 py-3">Absent</th><th class="px-4 py-3">Leave</th><th class="px-4 py-3">Exceptions</th><th class="px-4 py-3">Attendance</th><th class="px-5 py-3">Overtime</th></tr></thead><tbody class="divide-y divide-[var(--people-border)]"><tr v-for="row in (unitId ? data?.departments : data?.units)" :key="row.id"><td class="px-5 py-4 font-medium">{{ row.name }}</td><td class="px-4 py-4">{{ row.headcount }}</td><td class="px-4 py-4">{{ row.present }}</td><td class="px-4 py-4">{{ row.absent }}</td><td class="px-4 py-4">{{ row.on_leave }}</td><td class="px-4 py-4">{{ row.exceptions }}</td><td class="px-4 py-4"><UBadge color="neutral" variant="soft">{{ row.attendance_rate }}%</UBadge></td><td class="px-5 py-4">{{ formatHours(row.approved_overtime_minutes) }}</td></tr><tr v-if="!(unitId ? data?.departments : data?.units)?.length"><td colspan="8" class="px-5 py-10 text-center text-muted">No operational records match this filter.</td></tr></tbody></table></div></section>

    <section class="sr-only" aria-label="Attendance trend data"><table><caption>Attendance trend data</caption><thead><tr><th>Date</th><th>Present</th><th>Absent</th><th>On leave</th><th>Off or holiday</th></tr></thead><tbody><tr v-for="point in data?.trend" :key="point.date"><td>{{ point.date }}</td><td>{{ point.present }}</td><td>{{ point.absent }}</td><td>{{ point.on_leave }}</td><td>{{ point.weekly_off_or_holiday }}</td></tr></tbody></table></section>

    <UModal v-model:open="showExceptions" title="Employee exception drill-down"><template #body><div v-if="exceptionsPending" class="space-y-3"><USkeleton v-for="i in 5" :key="i" class="h-12 w-full" /></div><div v-else-if="!exceptions?.items.length" class="py-8 text-center text-sm text-muted">No employees match this exception.</div><template v-else><div class="divide-y divide-[var(--people-border)]"><NuxtLink v-for="employee in exceptions.items" :key="employee.id" :to="`/employees/${employee.id}`" class="block py-3 hover:bg-muted/5"><p class="font-medium">{{ employee.full_name || `${employee.first_name} ${employee.last_name || ''}` }}</p><p class="text-xs text-muted">{{ employee.employee_code }} · {{ employee.department_name || 'No department' }} · {{ employee.unit_name || 'No unit' }}</p></NuxtLink></div><div v-if="exceptions.total_pages > 1" class="mt-4 flex items-center justify-between gap-3"><p class="text-xs text-muted">Page {{ exceptions.page }} of {{ exceptions.total_pages }} · {{ exceptions.total }} employees</p><div class="flex gap-2"><UButton size="xs" color="neutral" variant="soft" :disabled="exceptionPage === 1" @click="exceptionPage -= 1">Previous</UButton><UButton size="xs" color="neutral" variant="soft" :disabled="exceptionPage === exceptions.total_pages" @click="exceptionPage += 1">Next</UButton></div></div></template></template></UModal>
  </section>
</template>
