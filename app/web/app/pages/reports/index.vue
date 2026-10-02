<script setup lang="ts">
const chartTheme = useChartTheme()
/* eslint-disable better-tailwindcss/no-unknown-classes, @stylistic/max-statements-per-line */
import type { AttendanceMatrix, LeaveSummary } from '#shared/types/report'

useSeoMeta({ title: 'Reports' })
const api = useHrmsApi()
const list = useListState({ sort_order: 'asc' })
const auth = useAuth()
const tab = ref<'attendance' | 'leave'>(auth.hasPermission('reports.attendance') ? 'attendance' : 'leave')
const month = list.field('month', new Date().toISOString().slice(0, 7))
const year = computed({
  get: () => Number(list.field('year', String(new Date().getFullYear())).value),
  set: value => { void list.update({ year: value }) }
})
const { data: rawData, pending, error, refresh } = await useAsyncData('reports', async () => {
  if (tab.value === 'attendance') {
    const [yearValue, monthValue] = month.value.split('-').map(Number)
    return {
      attendance: await api.request<AttendanceMatrix>('reports/attendance-matrix', {
        query: { ...list.query.value, year: yearValue, month: monthValue }
      }),
      leave: null
    }
  }
  return {
    attendance: null,
    leave: await api.request<LeaveSummary>('reports/leave-summary', {
      query: { ...list.query.value, year: year.value }
    })
  }
}, { watch: [tab, month, year, list.query] })
const data = useRetainedData(rawData)
watch([tab, month, year], () => {
  list.page.value = 1
})
const days = computed(() => Array.from({ length: data.value?.attendance?.total_days_in_month || 0 }, (_, index) => index + 1))
const statusClass = (value?: string) => ({ P: 'bg-[var(--people-mint)] text-[var(--people-mint-ink)]', A: 'bg-[var(--people-rose)] text-[var(--people-rose-ink)]', L: 'bg-[var(--people-lavender)] text-[var(--people-lavender-ink)]', HD: 'bg-[var(--people-yellow)] text-[var(--people-yellow-ink)]', WFH: 'bg-[var(--people-blue)] text-[var(--people-blue-ink)]', WO: 'bg-[var(--people-canvas)] text-muted', H: 'bg-[var(--people-peach)] text-[var(--people-peach-ink)]' }[value || ''] || 'text-muted')
const leaveChartOption = computed<ECOption>(() => {
  const totals = new Map<string, { allocated: number, used: number, pending: number }>()
  for (const row of data.value?.leave?.breakdown || []) {
    const current = totals.get(row.leave_type_name) || { allocated: 0, used: 0, pending: 0 }
    current.allocated += row.allocated
    current.used += row.used
    current.pending += row.pending
    totals.set(row.leave_type_name, current)
  }
  const types = [...totals.keys()]
  return {
    backgroundColor: 'transparent',
    animation: false,
    textStyle: { color: chartTheme.value ? '#beb2ce' : '#665e70' },
    tooltip: { confine: true, trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { top: 28, right: 20, bottom: 48, left: 42 },
    xAxis: { type: 'category', data: types, axisLabel: { interval: 0, rotate: types.length > 4 ? 25 : 0 } },
    yAxis: { type: 'value', name: 'Days' },
    series: [
      { name: 'Allocated', type: 'bar', data: types.map(type => totals.get(type)?.allocated || 0), itemStyle: { color: chartTheme.value ? '#c9b2ff' : '#5637a5' } },
      { name: 'Used', type: 'bar', data: types.map(type => totals.get(type)?.used || 0), itemStyle: { color: chartTheme.value ? '#94d8b4' : '#226747' } },
      { name: 'Pending', type: 'bar', data: types.map(type => totals.get(type)?.pending || 0), itemStyle: { color: chartTheme.value ? '#efd184' : '#805900' } }
    ]
  }
})
</script>

<template>
  <div class="people-page">
    <DataFeedback :pending="pending" :error="error" :has-data="Boolean(tab === 'attendance' ? data?.attendance : data?.leave)" />
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 class="mt-1 text-2xl font-semibold sm:text-3xl">
          Reports
        </h1><p class="mt-2 text-sm text-muted">
          Inspect monthly attendance and annual leave balances.
        </p>
      </div><UFormField :label="tab === 'attendance' ? 'Month' : 'Year'">
      <UInput
        v-if="tab === 'attendance'"
        v-model="month"
        type="month"
        icon="i-lucide-calendar-range"
      /><UInput
        v-else
        v-model.number="year"
        type="number"
        :min="2020"
        :max="2100"
        icon="i-lucide-calendar"
      />
      </UFormField>
    </div><div data-page-tabs class="mt-7 flex gap-2 border-b border-[var(--people-border)]">
      <button
        v-if="auth.hasPermission('reports.attendance')"
        class="min-h-11 border-b-2 px-3 text-sm font-semibold"
        :class="tab === 'attendance' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        :aria-pressed="tab === 'attendance'"
        @click="tab = 'attendance'"
      >
        Attendance matrix
      </button><button
        v-if="auth.hasPermission('reports.leave')"
        class="min-h-11 border-b-2 px-3 text-sm font-semibold"
        :class="tab === 'leave' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        :aria-pressed="tab === 'leave'"
        @click="tab = 'leave'"
      >
        Leave summary
      </button>
    </div>
    <ListControls
      v-model:search="list.search.value"
      v-model:sort-by="list.sortBy.value"
      v-model:sort-order="list.sortOrder.value"
      :active="list.active.value"
      :sorts="[{ label: 'Employee code', value: 'employee_code' }, { label: 'Name', value: 'name' }]"
      search-placeholder="Search employee name or code"
      @clear="list.clear"
    />
    <UAlert
      v-if="error"
      class="mt-5"
      color="error"
      variant="soft"
      title="Report is unavailable"
      :actions="[{ label: 'Try again', onClick: () => refresh() }]"
    /><div
      v-if="pending && !(tab === 'attendance' ? data?.attendance : data?.leave)"
      class="people-card mt-5 p-5"
    >
      <USkeleton class="h-96" />
    </div><section
      v-else-if="tab === 'attendance' && data?.attendance"
      class="people-card mt-5 overflow-hidden"
    >
      <div class="overflow-x-auto" role="region" aria-label="Attendance comparison table, scroll horizontally for all days" tabindex="0">
        <table class="min-w-max text-center text-xs">
          <thead class="sticky top-0 bg-[var(--people-surface)]">
            <tr>
              <th class="sticky left-0 z-10 min-w-56 bg-[var(--people-surface)] px-5 py-3 text-left">
                Employee
              </th><th
                v-for="day in days"
                :key="day"
                class="w-9 px-1 py-3"
              >
                {{ day }}
              </th><th class="px-3">
                P
              </th><th class="px-3">
                A
              </th><th class="px-3">
                Leave
              </th>
            </tr>
          </thead><tbody class="divide-y divide-[var(--people-border)]">
            <tr
              v-for="row in data?.attendance?.items"
              :key="row.employee_id"
            >
              <td class="sticky left-0 bg-[var(--people-surface)] px-5 py-3 text-left">
                <p class="font-semibold">
                  {{ row.employee_name }}
                </p><p class="mt-1 text-muted">
                  {{ row.employee_code }} · {{ row.department_name || '—' }}
                </p>
              </td><td
                v-for="day in days"
                :key="day"
                class="p-1"
              >
                <span
                  class="grid size-7 place-items-center rounded-md font-semibold"
                  :class="statusClass(row.day_status_map[day])"
                >{{ row.day_status_map[day] || '·' }}</span>
              </td><td class="px-3 font-semibold">
                {{ row.total_present }}
              </td><td class="px-3 font-semibold">
                {{ row.total_absent }}
              </td><td class="px-3 font-semibold">
                {{ row.total_leave }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section><section
      v-else-if="tab === 'leave' && data?.leave"
      class="people-card mt-5 overflow-hidden"
    >
      <div class="border-b border-[var(--people-border)] p-5 sm:px-6">
        <h3 class="font-semibold">
          Leave allocation and usage
        </h3>
        <p class="mt-1 text-sm text-muted">
          Totals by leave type for {{ year }}. The detailed balances remain available below.
        </p>
        <ClientOnly>
          <VChart :theme="chartTheme"
            class="mt-4 h-72 w-full"
            :option="leaveChartOption"
            autoresize
            aria-label="Leave allocation, usage, and pending requests by leave type"
          />
          <template #fallback>
            <USkeleton class="mt-4 h-72 w-full" />
          </template>
        </ClientOnly>
      </div>
      <div class="hidden overflow-x-auto md:block">
        <table class="w-full min-w-[720px] text-left text-sm">
          <thead class="bg-muted/5 text-xs uppercase text-muted">
            <tr>
              <th class="px-6 py-3">
                Employee
              </th><th class="px-4">
                Leave type
              </th><th class="px-4 text-right">
                Allocated
              </th><th class="px-4 text-right">
                Used
              </th><th class="px-4 text-right">
                Pending
              </th><th class="px-6 text-right">
                Available
              </th>
            </tr>
          </thead><tbody class="divide-y divide-[var(--people-border)]">
            <tr
              v-for="row in data?.leave?.items"
              :key="`${row.employee_id}-${row.leave_type_code}`"
            >
              <td class="px-6 py-4">
                <p class="font-semibold">
                  {{ row.employee_name }}
                </p><p class="text-xs text-muted">
                  {{ row.employee_code }}
                </p>
              </td><td class="px-4">
                {{ row.leave_type_name }}
              </td><td class="px-4 text-right">
                {{ row.allocated }}
              </td><td class="px-4 text-right">
                {{ row.used }}
              </td><td class="px-4 text-right">
                {{ row.pending }}
              </td><td class="px-6 text-right font-semibold">
                {{ row.available }}
              </td>
            </tr>
          </tbody>
        </table>
      </div><div class="divide-y divide-[var(--people-border)] md:hidden">
        <article
          v-for="row in data?.leave?.items"
          :key="`${row.employee_id}-${row.leave_type_code}`"
          class="p-5"
        >
          <div class="flex justify-between">
            <div>
              <p class="font-semibold">
                {{ row.employee_name }}
              </p><p class="mt-1 text-xs text-muted">
                {{ row.leave_type_name }}
              </p>
            </div><p class="text-2xl font-semibold">
              {{ row.available }}
            </p>
          </div><div class="mt-4 grid grid-cols-3 text-xs text-muted">
            <span>{{ row.allocated }} allocated</span><span>{{ row.used }} used</span><span>{{ row.pending }} pending</span>
          </div>
        </article>
      </div>
    </section>
    <ListPagination v-if="tab === 'attendance' ? data?.attendance : data?.leave" v-model:page="list.page.value" v-model:page-size="list.pageSize.value" :total="(data?.attendance || data?.leave)?.total || 0" :total-pages="(data?.attendance || data?.leave)?.total_pages" :loading="pending" label="employees" />
  </div>
</template>
