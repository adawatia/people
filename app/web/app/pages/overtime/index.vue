<script setup lang="ts">
import type { OvertimePage, OvertimeSummary } from '#shared/types/overtime'

const chartTheme = useChartTheme()

useSeoMeta({ title: 'Overtime' })
const auth = useAuth()
const workspace = useWorkspace()
const api = useHrmsApi()
const employeeId = computed(() => auth.user.value?.employee_id)
const selfService = computed(() => workspace.current.value === 'MY')
const list = useListState({ month: new Date().toISOString().slice(0, 7), status: 'ALL', sort_order: 'desc' })
const selectedMonth = list.field('month')
const statusFilter = list.field('status')
const page = list.page
const search = list.search
const { data, pending, error, refresh } = useLazyAsyncData('my-overtime', async (_app, { signal }) => {
  if (selfService.value && !employeeId.value) return null
  const parts = selectedMonth.value.split('-').map(Number)
  const hasMonth = /^\d{4}-(0[1-9]|1[0-2])$/.test(selectedMonth.value)
  const summaryRequest = selfService.value && employeeId.value && hasMonth
    ? api.request<OvertimeSummary>(`overtime/employee/${employeeId.value}/summary`, { query: { year: parts[0], month: parts[1] } })
    : Promise.resolve(null)
  const recordsRequest = api.request<OvertimePage>('overtime/', {
    signal, query: {
      employee_id: selfService.value ? employeeId.value : undefined,
      ...list.query.value,
      status: statusFilter.value === 'ALL' ? undefined : statusFilter.value,
      from_date: hasMonth ? `${selectedMonth.value}-01` : undefined,
      to_date: hasMonth ? `${selectedMonth.value}-${new Date(parts[0]!, parts[1]!, 0).getDate()}` : undefined
    }
  })
  const [summary, records] = await Promise.all([summaryRequest, recordsRequest])
  return { summary, records }
}, { watch: [employeeId, selectedMonth, selfService, statusFilter, list.query] })
const filtered = computed(() => data.value?.records.items || [])
const hours = (minutes: number) => `${Math.floor(minutes / 60)}h ${minutes % 60}m`
const statusColor = (value: string) => ({ PENDING: 'warning', APPROVED: 'success', REJECTED: 'error' }[value] || 'neutral') as 'warning' | 'success' | 'error' | 'neutral'
const overtimeChartOption = computed<ECOption>(() => ({
  tooltip: { trigger: 'axis', valueFormatter: value => `${value} hours` },
  grid: { top: 20, right: 16, bottom: 28, left: 42 },
  xAxis: { type: 'category', data: ['Calculated', 'Approved'] },
  yAxis: { type: 'value', name: 'Hours' },
  series: [{
    name: 'Overtime',
    type: 'bar',
    barMaxWidth: 64,
    data: [
      { value: Number(((data.value?.summary?.total_calculated_minutes || 0) / 60).toFixed(1)), itemStyle: { color: '#2563eb' } },
      { value: Number(((data.value?.summary?.total_approved_minutes || 0) / 60).toFixed(1)), itemStyle: { color: '#10b981' } }
    ]
  }]
}))
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          {{ selfService ? 'My Workspace' : workspace.current.value === 'TEAM' ? 'Team Workspace' : 'HR Workspace' }}
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          {{ selfService ? 'My overtime' : 'Overtime records' }}
        </h2><p class="mt-2 text-sm text-muted">
          {{ selfService ? 'Review your calculated hours and approval status.' : 'Review overtime records within your authorized scope.' }}
        </p>
      </div>
      <UInput
        v-model="selectedMonth"
        type="month"
        min="2000-01"
        max="2100-12"
        aria-label="Overtime month"
        icon="i-lucide-calendar-range"
        class="w-full sm:w-48"
      />
    </div>
    <UAlert
      v-if="selfService && !employeeId"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-user-round-x"
      title="No employee profile is linked"
    />
    <UAlert
      v-else-if="error"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-coffee"
      title="Your overtime details are taking a short break"
      description="We couldn’t refresh your overtime details right now. Please try again in a moment."
      :actions="[{ label: 'Refresh overtime', onClick: () => refresh() }]"
    />
    <template v-else-if="selfService ? employeeId : true">
      <section
        v-if="selfService"
        class="mt-7 grid gap-4 sm:grid-cols-3"
      >
        <article
          v-for="metric in [{ label: 'Calculated', value: hours(data?.summary?.total_calculated_minutes || 0), icon: 'i-lucide-timer', bg: 'var(--people-blue)' }, { label: 'Approved', value: hours(data?.summary?.total_approved_minutes || 0), icon: 'i-lucide-circle-check', bg: 'var(--people-mint)' }, { label: 'Pending reviews', value: String(data?.summary?.pending_count || 0), icon: 'i-lucide-hourglass', bg: 'var(--people-peach)' }]"
          :key="metric.label"
          class="people-card p-5"
        >
          <div class="flex items-center justify-between">
            <p class="text-sm text-muted">
              {{ metric.label }}
            </p><span
              class="grid size-10 place-items-center rounded-xl"
              :style="{ background: metric.bg }"
            ><UIcon
              :name="metric.icon"
              class="size-5"
            /></span>
          </div><p class="mt-5 text-3xl font-semibold tabular-nums">
            {{ pending ? '—' : metric.value }}
          </p>
        </article>
      </section>
      <section
        v-if="selfService"
        class="people-card mt-7 p-5 sm:px-6"
      >
        <h3 class="font-semibold">
          Overtime hours
        </h3>
        <p class="mt-1 text-sm text-muted">
          Calculated hours compared with approved hours for the selected month.
        </p>
        <ClientOnly>
          <VChart
            :theme="chartTheme"
            class="mt-4 h-56 w-full"
            :option="overtimeChartOption"
            autoresize
            aria-label="Calculated and approved overtime hours comparison"
          />
          <template #fallback>
            <USkeleton class="mt-4 h-56 w-full" />
          </template>
        </ClientOnly>
      </section>
      <section class="people-card mt-7 overflow-hidden">
        <div
          v-if="!selfService"
          class="px-5 pt-5"
        >
          <UInput
            v-model="search"
            icon="i-lucide-search"
            placeholder="Search employee name or code"
            aria-label="Search overtime by employee"
            class="w-full sm:w-80"
          />
        </div>
        <div class="flex flex-col gap-4 border-b border-[var(--people-border)] p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <h3 class="font-semibold">
              Overtime records
            </h3><p class="mt-1 text-sm text-muted">
              Calculated from processed attendance
            </p>
          </div><div class="flex gap-1 overflow-x-auto rounded-xl bg-muted/5 p-1">
            <button
              v-for="option in ['ALL', 'PENDING', 'APPROVED', 'REJECTED']"
              :key="option"
              class="rounded-lg px-3 py-2 text-xs font-semibold"
              :class="statusFilter === option ? 'bg-[var(--people-surface)] shadow-sm' : 'text-muted'"
              @click="statusFilter = option"
            >
              {{ option }}
            </button>
          </div>
        </div>
        <div
          v-if="pending"
          class="space-y-3 p-5"
        >
          <USkeleton
            v-for="i in 4"
            :key="i"
            class="h-16 w-full"
          />
        </div>
        <div
          v-else-if="!filtered.length"
          class="p-10 text-center"
        >
          <UIcon
            name="i-lucide-timer-off"
            class="mx-auto size-9 text-muted"
          /><p class="mt-3 font-medium">
            No overtime records
          </p><p class="mt-1 text-sm text-muted">
            Processed overtime for this filter will appear here.
          </p>
        </div>
        <div
          v-else
          class="divide-y divide-[var(--people-border)]"
        >
          <article
            v-for="item in filtered"
            :key="item.id"
            class="grid gap-4 p-5 sm:grid-cols-[1fr_auto_auto] sm:items-center sm:px-6"
          >
            <div>
              <p class="font-medium">
                {{ selfService ? item.attendance_date || `Attendance record #${item.attendance_record_id}` : item.employee_name || `Employee #${item.employee_id}` }}
              </p><p class="mt-1 text-xs text-muted">
                {{ item.employee_code }} · {{ item.attendance_date }} · Reference #{{ item.id }}
              </p>
            </div><div class="grid grid-cols-2 gap-5 text-sm sm:text-right">
              <div>
                <p class="text-xs text-muted">
                  Calculated
                </p><p class="mt-1 font-semibold tabular-nums">
                  {{ hours(item.calculated_minutes) }}
                </p>
              </div><div>
                <p class="text-xs text-muted">
                  Approved
                </p><p class="mt-1 font-semibold tabular-nums">
                  {{ hours(item.approved_minutes) }}
                </p>
              </div>
            </div><UBadge
              :color="statusColor(item.status)"
              variant="soft"
            >
              {{ item.status }}
            </UBadge><p
              v-if="item.rejection_reason"
              class="text-sm text-error sm:col-span-3"
            >
              {{ item.rejection_reason }}
            </p>
          </article>
        </div>
        <div
          v-if="data?.records"
          class="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--people-border)] p-5"
        >
          <p class="text-sm text-muted">
            {{ data.records.total }} records · Page {{ data.records.page }} of {{ data.records.total_pages }}
          </p>
          <div class="flex gap-2">
            <UButton
              color="neutral"
              variant="soft"
              :disabled="pending || !data.records.has_prev"
              @click="page -= 1"
            >
              Previous
            </UButton>
            <UButton
              color="neutral"
              variant="soft"
              :disabled="pending || !data.records.has_next"
              @click="page += 1"
            >
              Next
            </UButton>
          </div>
        </div>
      </section>
    </template>
    <ListPagination
      v-if="data?.records"
      v-model:page="list.page.value"
      v-model:page-size="list.pageSize.value"
      :total="data?.records?.total || 0"
      :total-pages="data?.records?.total_pages"
      :loading="pending"
    />
  </div>
</template>
