<script setup lang="ts">
import type { OwnerDashboard, OwnerExceptionResponse } from '#shared/types/dashboard'

const chartTheme = useChartTheme()
const mode = useColorMode()
const api = useHrmsApi()
const today = new Date().toISOString().slice(0, 10)
const rangeStart = new Date(Date.now() - 29 * 86_400_000).toISOString().slice(0, 10)
const ownerFilters = useListState({ from_date: rangeStart, to_date: today, unit_id: '0' }, 'owner_')
const fromDate = ownerFilters.field('from_date')
const toDate = ownerFilters.field('to_date')
const unitId = computed({
  get: () => Number(ownerFilters.field('unit_id').value) || 0,
  set: (value) => { ownerFilters.field('unit_id').value = value > 0 ? String(value) : '0' }
})
const dateError = computed(() => {
  if (!fromDate.value || !toDate.value) return 'Enter both a start and an end date.'
  const start = Date.parse(fromDate.value)
  const end = Date.parse(toDate.value)
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 'Enter valid dates.'
  if (start > end) return 'Start date must be on or before end date.'
  if ((end - start) / 86_400_000 > 366) return 'Date range cannot exceed 366 days.'
  return ''
})
const filtersChanged = computed(() => fromDate.value !== rangeStart || toDate.value !== today || unitId.value !== 0)
const applied = ref({ from: rangeStart, to: today, unit: 0 })
watch([fromDate, toDate, unitId], () => {
  if (dateError.value) return
  const next = { from: fromDate.value, to: toDate.value, unit: unitId.value }
  if (JSON.stringify(next) !== JSON.stringify(applied.value)) applied.value = next
})
function resetFilters() {
  ownerFilters.clear()
}
const { data: response, pending, error, refresh } = useLazyAsyncData(
  'owner-dashboard',
  () => api.request<OwnerDashboard>('dashboard/owner', { query: { from_date: applied.value.from, to_date: applied.value.to, unit_id: applied.value.unit || undefined } }),
  { watch: [applied] }
)
const lastData = shallowRef<OwnerDashboard>()
const loadedUnit = ref(0)
watch(response, (value) => {
  if (value) {
    lastData.value = value
    loadedUnit.value = applied.value.unit
  }
}, { immediate: true })
const data = computed(() => response.value || lastData.value)
const performanceRows = computed(() => (loadedUnit.value ? data.value?.departments : data.value?.units) || [])
const selectedDayLabel = computed(() => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' }).format(new Date(`${data.value?.to_date || applied.value.to}T00:00:00`)))
const formatHours = (minutes: number) => `${(minutes / 60).toFixed(1)}h`
const exceptionKind = ref<'absent' | 'late' | 'late_or_missed_punch' | 'missed_punch' | 'on_leave' | 'pending_request'>('absent')
const exceptionPage = ref(1)
const showExceptions = ref(false)
const exceptionTrigger = shallowRef<HTMLElement>()
const { data: exceptions, pending: exceptionsPending, error: exceptionsError, refresh: refreshExceptions } = useLazyAsyncData(
  'owner-dashboard-exceptions',
  () => api.request<OwnerExceptionResponse>('dashboard/owner/exceptions', { query: { kind: exceptionKind.value, target_date: data.value?.to_date || applied.value.to, unit_id: loadedUnit.value || undefined, page: exceptionPage.value } }),
  { immediate: false }
)
async function openExceptions(kind: typeof exceptionKind.value, event: MouseEvent) {
  exceptionTrigger.value = event.currentTarget as HTMLElement
  exceptionKind.value = kind
  exceptionPage.value = 1
  showExceptions.value = true
  await refreshExceptions()
}
async function changeExceptionPage(delta: number) {
  if (exceptionsPending.value) return
  exceptionPage.value += delta
  await refreshExceptions()
}
watch(showExceptions, async (open) => {
  if (!open) {
    await nextTick()
    exceptionTrigger.value?.focus()
  }
})
const exceptionLabels = { absent: 'Absent employees', late_or_missed_punch: 'Late or missed punches', on_leave: 'Employees on leave', pending_request: 'Pending requests', late: 'Late employees', missed_punch: 'Missed punches' }
const metrics = computed(() => [
  { label: 'Active workforce', value: data.value?.summary.active_headcount ?? 0, icon: 'i-lucide-users-round' },
  { label: `Present on ${selectedDayLabel.value}`, value: data.value?.summary.present ?? 0, icon: 'i-lucide-circle-check-big' },
  { label: `Absent on ${selectedDayLabel.value}`, value: data.value?.summary.absent ?? 0, icon: 'i-lucide-calendar-x-2' },
  { label: 'On leave', value: data.value?.summary.on_leave ?? 0, icon: 'i-lucide-calendar-heart' },
  { label: 'Attendance rate', value: `${data.value?.summary.attendance_rate ?? 0}%`, icon: 'i-lucide-chart-no-axes-combined' },
  { label: 'Open exceptions', value: data.value?.summary.late_or_missed_punches ?? 0, icon: 'i-lucide-triangle-alert' }
])
const trendOption = computed<ECOption>(() => {
  const dark = mode.value === 'dark'
  const text = dark ? '#beb2ce' : '#665e70'
  return {
    animation: false,
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'system-ui, sans-serif', color: text },
    tooltip: { confine: true, trigger: 'axis' },
    legend: { bottom: 0, textStyle: { color: text }, itemWidth: 12, itemHeight: 12 },
    grid: { left: 36, right: 12, top: 16, bottom: 76, containLabel: true },
    xAxis: { type: 'category', axisLabel: { color: text, hideOverlap: true }, data: data.value?.trend.map(item => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' }).format(new Date(`${item.date}T00:00:00`))) || [] },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: text }, splitLine: { lineStyle: { color: dark ? '#51465e' : '#ded8e5' } } },
    series: [
      { name: 'Present', type: 'bar', stack: 'attendance', data: data.value?.trend.map(item => item.present) || [], itemStyle: { color: dark ? '#94d8b4' : '#226747' } },
      { name: 'Absent', type: 'bar', stack: 'attendance', data: data.value?.trend.map(item => item.absent) || [], itemStyle: { color: dark ? '#f2acbd' : '#a52b46' } },
      { name: 'On leave', type: 'bar', stack: 'attendance', data: data.value?.trend.map(item => item.on_leave) || [], itemStyle: { color: dark ? '#c4b5fd' : '#5637a5' } },
      { name: 'Off / holiday', type: 'bar', stack: 'attendance', data: data.value?.trend.map(item => item.weekly_off_or_holiday) || [], itemStyle: { color: text } }
    ]
  }
})
</script>

<template>
  <section
    class="dashboard-owner"
    aria-label="Organization analytics"
  >
    <div
      class="dashboard-filters"
      aria-label="Analytics filters"
    >
      <UFormField
        label="Start date"
        :error="dateError || undefined"
      >
        <UInput
          v-model="fromDate"
          type="date"
          aria-label="Analytics start date"
          :aria-invalid="Boolean(dateError)"
          aria-describedby="analytics-date-error"
          class="w-full"
        />
      </UFormField>
      <UFormField label="End date">
        <UInput
          v-model="toDate"
          type="date"
          aria-label="Analytics end date"
          :aria-invalid="Boolean(dateError)"
          aria-describedby="analytics-date-error"
          class="w-full"
        />
      </UFormField>
      <div class="dashboard-filter-unit">
        <label
          class="text-sm font-medium"
          for="analytics-unit"
        >Unit</label>
        <div class="dashboard-filter-unit-controls">
          <RemoteSelect
            id="analytics-unit"
            v-model="unitId"
            endpoint="org/units"
            label="All units"
          />
          <UButton
            v-if="unitId"
            color="neutral"
            variant="ghost"
            aria-label="Clear unit"
            @click="unitId = 0"
          >
            Clear unit
          </UButton>
        </div>
      </div>
      <p
        v-if="dateError"
        id="analytics-date-error"
        class="dashboard-filter-error"
        role="alert"
      >
        {{ dateError }}
      </p>
      <div class="dashboard-filter-actions">
        <UButton
          icon="i-lucide-refresh-cw"
          color="primary"
          variant="soft"
          :loading="pending"
          :disabled="pending || Boolean(dateError)"
          @click="() => refresh()"
        >
          Refresh
        </UButton>
        <UButton
          v-if="filtersChanged"
          icon="i-lucide-rotate-ccw"
          color="neutral"
          variant="ghost"
          @click="resetFilters"
        >
          Reset filters
        </UButton>
        <span
          v-if="pending"
          class="dashboard-sync"
          role="status"
        >{{ data ? 'Updating analytics…' : 'Loading analytics…' }}</span>
      </div>
    </div>
    <p class="dashboard-sync">
      ERP attendance last synced: {{ data?.attendance_last_synced_at ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(data.attendance_last_synced_at)) : data ? 'No sync timestamp available' : 'Unavailable' }}
    </p>
    <UAlert
      v-if="error"
      color="error"
      title="Organization analytics could not be loaded"
      description="Please retry. Any displayed results are from the last successful update."
      :actions="[{ label: 'Retry analytics', disabled: pending || Boolean(dateError), onClick: () => refresh() }]"
    />
    <DashboardSummary
      :items="metrics"
      variant="executive"
      :pending="pending"
      :unavailable="!data"
    />
    <div class="dashboard-columns dashboard-columns--owner">
      <section
        class="dashboard-panel"
        :aria-busy="pending"
      >
        <h2>Attendance trend</h2>
        <p class="dashboard-description">
          Daily attendance composition; a text alternative follows below.
        </p>
        <USkeleton
          v-if="pending && !data"
          class="dashboard-chart"
        />
        <ClientOnly v-else-if="data">
          <VChart
            :theme="chartTheme"
            class="dashboard-chart"
            :option="trendOption"
            autoresize
          />
          <template #fallback>
            <USkeleton class="dashboard-chart" />
          </template>
        </ClientOnly>
        <div
          v-else
          class="dashboard-empty"
        >
          <p>Attendance trend is unavailable.</p>
        </div>
      </section>
      <section class="dashboard-panel">
        <h2>Needs attention</h2>
        <p class="dashboard-description">
          Review employees in each exception group.
        </p>
        <div class="dashboard-attention">
          <button
            type="button"
            :disabled="!data || pending"
            @click="openExceptions('absent', $event)"
          >
            <span>{{ data?.summary.absent ?? '—' }} absent on {{ selectedDayLabel }}</span><UIcon
              name="i-lucide-arrow-up-right"
              class="size-4 shrink-0"
            />
          </button>
          <button
            type="button"
            :disabled="!data || pending"
            @click="openExceptions('late_or_missed_punch', $event)"
          >
            <span>{{ data?.summary.late_or_missed_punches ?? '—' }} late or missed punches</span><UIcon
              name="i-lucide-arrow-up-right"
              class="size-4 shrink-0"
            />
          </button>
          <button
            type="button"
            :disabled="!data || pending"
            @click="openExceptions('on_leave', $event)"
          >
            <span>{{ data?.summary.on_leave ?? '—' }} employees on leave</span><UIcon
              name="i-lucide-arrow-up-right"
              class="size-4 shrink-0"
            />
          </button>
          <button
            type="button"
            :disabled="!data || pending"
            @click="openExceptions('pending_request', $event)"
          >
            <span>{{ data?.summary.pending_requests ?? '—' }} pending requests</span><UIcon
              name="i-lucide-arrow-up-right"
              class="size-4 shrink-0"
            />
          </button>
        </div>
        <div class="dashboard-overtime">
          <p>Approved overtime in selected period</p><strong>{{ data ? formatHours(data.summary.approved_overtime_minutes) : '—' }}</strong>
        </div>
      </section>
    </div>
    <section
      class="dashboard-panel dashboard-performance"
      :aria-busy="pending"
    >
      <div class="dashboard-performance-heading">
        <h2>{{ loadedUnit ? 'Department performance' : 'Unit performance' }}</h2><p class="dashboard-description">
          Select a unit above to compare its departments.
        </p>
      </div>
      <USkeleton
        v-if="pending && !data"
        class="m-5 h-32"
      />
      <template v-else-if="performanceRows.length">
        <div
          class="dashboard-performance-table"
          tabindex="0"
          aria-label="Performance comparison table"
        >
          <table>
            <caption class="sr-only">
              {{ loadedUnit ? 'Department' : 'Unit' }} performance
            </caption><thead>
              <tr>
                <th scope="col">
                  Group
                </th><th scope="col">
                  Headcount
                </th><th scope="col">
                  Present
                </th><th scope="col">
                  Absent
                </th><th scope="col">
                  Leave
                </th><th scope="col">
                  Exceptions
                </th><th scope="col">
                  Attendance
                </th><th scope="col">
                  Overtime
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in performanceRows"
                :key="row.id"
              >
                <th scope="row">
                  {{ row.name }}
                </th><td>{{ row.headcount }}</td><td>{{ row.present }}</td><td>{{ row.absent }}</td><td>{{ row.on_leave }}</td><td>{{ row.exceptions }}</td><td>{{ row.attendance_rate }}%</td><td>{{ formatHours(row.approved_overtime_minutes) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="dashboard-performance-records">
          <article
            v-for="row in performanceRows"
            :key="row.id"
            class="dashboard-performance-record"
          >
            <h3>{{ row.name }}</h3><dl><div><dt>Headcount</dt><dd>{{ row.headcount }}</dd></div><div><dt>Present</dt><dd>{{ row.present }}</dd></div><div><dt>Absent</dt><dd>{{ row.absent }}</dd></div><div><dt>Leave</dt><dd>{{ row.on_leave }}</dd></div><div><dt>Exceptions</dt><dd>{{ row.exceptions }}</dd></div><div><dt>Attendance</dt><dd>{{ row.attendance_rate }}%</dd></div><div><dt>Overtime</dt><dd>{{ formatHours(row.approved_overtime_minutes) }}</dd></div></dl>
          </article>
        </div>
      </template>
      <div
        v-else
        class="dashboard-empty"
      >
        <p>{{ data ? 'No operational records match this filter.' : 'Performance information is unavailable.' }}</p>
      </div>
    </section>
    <section
      class="sr-only"
      aria-label="Attendance trend data"
    >
      <table>
        <caption>Attendance trend data</caption><thead><tr><th>Date</th><th>Present</th><th>Absent</th><th>On leave</th><th>Off or holiday</th></tr></thead><tbody>
          <tr
            v-for="point in data?.trend"
            :key="point.date"
          >
            <td>{{ point.date }}</td><td>{{ point.present }}</td><td>{{ point.absent }}</td><td>{{ point.on_leave }}</td><td>{{ point.weekly_off_or_holiday }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <UModal
      v-model:open="showExceptions"
      :title="exceptionLabels[exceptionKind]"
      :description="`Employee exception drill-down · ${selectedDayLabel}`"
      close
      :ui="{ close: 'min-h-11 min-w-11', body: 'max-h-[70dvh] overflow-y-auto' }"
    >
      <template #close>
        <UButton
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          aria-label="Close exceptions"
          class="min-h-11 min-w-11"
          @click="showExceptions = false"
        />
      </template>
      <template #body>
        <div
          class="dashboard-exceptions"
          :aria-busy="exceptionsPending"
        >
          <div
            v-if="exceptionsPending"
            class="space-y-3"
          >
            <p
              role="status"
              class="dashboard-sync"
            >
              Loading employees…
            </p><USkeleton
              v-for="i in 3"
              :key="i"
              class="h-16 w-full"
            />
          </div>
          <UAlert
            v-else-if="exceptionsError"
            title="Employee exceptions could not be loaded"
            color="error"
            :actions="[{ label: 'Retry exceptions', onClick: () => refreshExceptions() }]"
          />
          <div
            v-else-if="!exceptions?.items.length"
            class="dashboard-empty"
          >
            <p>No employees match this exception.</p>
          </div>
          <template v-else>
            <NuxtLink
              v-for="employee in exceptions.items"
              :key="employee.id"
              :to="`/employees/${employee.id}`"
              class="dashboard-exception-link"
            ><p>{{ employee.full_name || `${employee.first_name} ${employee.last_name || ''}` }}</p><small>{{ employee.employee_code }} · {{ employee.department_name || 'No department' }} · {{ employee.unit_name || 'No unit' }}</small></NuxtLink>
          </template>
          <div
            v-if="exceptions && !exceptionsError"
            class="dashboard-pagination"
          >
            <p>Page {{ exceptions.page }} of {{ exceptions.total_pages || 1 }} · {{ exceptions.total }} employees</p><div>
              <UButton
                color="neutral"
                variant="outline"
                :disabled="exceptionsPending || exceptionPage <= 1"
                @click="changeExceptionPage(-1)"
              >
                Previous
              </UButton><UButton
                color="neutral"
                variant="outline"
                :disabled="exceptionsPending || exceptionPage >= exceptions.total_pages"
                @click="changeExceptionPage(1)"
              >
                Next
              </UButton>
            </div>
          </div>
        </div>
      </template>
    </UModal>
  </section>
</template>
