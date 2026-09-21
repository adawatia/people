<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
import type { AttendanceCorrection, AttendanceRecord, AttendanceSummary } from '#shared/types/attendance'

useSeoMeta({ title: 'Attendance' })
const auth = useAuth()
const api = useHrmsApi()
const toast = useToast()
const employeeId = computed(() => auth.user.value?.employee_id)
const monthCursor = ref(new Date(new Date().getFullYear(), new Date().getMonth(), 1))
const correctionRecord = ref<AttendanceRecord | null>(null)
const correction = reactive({ requested_punch_in: '', requested_punch_out: '', reason: '' })
const correctionLoading = ref(false)

function dateKey(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const monthKey = computed(() => `${monthCursor.value.getFullYear()}-${monthCursor.value.getMonth() + 1}`)
const monthLabel = computed(() => new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric' }).format(monthCursor.value))

const { data: attendanceData, pending, error, refresh } = await useAsyncData(
  'my-attendance',
  async () => {
    if (!employeeId.value) return null
    const year = monthCursor.value.getFullYear()
    const month = monthCursor.value.getMonth() + 1
    const first = new Date(year, month - 1, 1)
    const last = new Date(year, month, 0)
    const [records, summary, corrections] = await Promise.all([
      api.request<AttendanceRecord[]>(`attendance/employee/${employeeId.value}/calendar`, { query: { year, month } }),
      api.request<AttendanceSummary>(`attendance/employee/${employeeId.value}/summary`, { query: { year, month } }),
      api.request<AttendanceCorrection[]>('attendance/corrections')
    ])
    return { records, summary, corrections, first: dateKey(first), last: dateKey(last) }
  },
  { watch: [monthKey, employeeId] }
)

const records = computed(() => attendanceData.value?.records || [])
const recordMap = computed(() => new Map(records.value.map(record => [record.attendance_date, record])))
const calendarDays = computed(() => {
  const year = monthCursor.value.getFullYear()
  const month = monthCursor.value.getMonth()
  const firstDay = new Date(year, month, 1)
  const offset = (firstDay.getDay() + 6) % 7
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const days: Array<{ date: Date, key: string, currentMonth: boolean, record?: AttendanceRecord }> = []
  for (let index = -offset; index < daysInMonth + (7 - ((offset + daysInMonth) % 7 || 7)); index++) {
    const date = new Date(year, month, index + 1)
    const key = dateKey(date)
    days.push({ date, key, currentMonth: date.getMonth() === month, record: recordMap.value.get(key) })
  }
  return days
})

const summaryCards = computed(() => {
  const summary = attendanceData.value?.summary
  return [
    { label: 'Attendance', value: `${summary?.attendance_percentage ?? 0}%`, note: `${summary?.total_present ?? 0} days present`, icon: 'i-lucide-gauge', tone: 'var(--people-mint)' },
    { label: 'Working days', value: summary?.total_working_days ?? 0, note: `${summary?.total_half_day ?? 0} half days`, icon: 'i-lucide-calendar-range', tone: 'var(--people-blue)' },
    { label: 'Late arrivals', value: summary?.total_late ?? 0, note: `${summary?.total_early_exit ?? 0} early exits`, icon: 'i-lucide-clock-alert', tone: 'var(--people-peach)' },
    { label: 'Overtime', value: formatDuration(summary?.total_overtime_minutes ?? 0), note: `${summary?.total_missed_punch ?? 0} missed punches`, icon: 'i-lucide-timer-reset', tone: 'var(--people-lavender)' }
  ]
})

const statusSegments = computed(() => {
  const summary = attendanceData.value?.summary
  return [
    { label: 'Present', value: summary?.total_present ?? 0, color: '#10b981' },
    { label: 'Half day', value: summary?.total_half_day ?? 0, color: '#8b5cf6' },
    { label: 'Leave', value: summary?.total_leave ?? 0, color: '#6366f1' },
    { label: 'Absent', value: summary?.total_absent ?? 0, color: '#f43f5e' },
    { label: 'Other', value: (summary?.total_holiday ?? 0) + (summary?.total_weekly_off ?? 0), color: '#94a3b8' }
  ]
})

const chartTotal = computed(() => statusSegments.value.reduce((total, segment) => total + segment.value, 0))
const attendanceChartOption = computed<ECOption>(() => ({
  tooltip: {
    trigger: 'item',
    valueFormatter: value => `${value} days`
  },
  series: [{
    name: 'Attendance status',
    type: 'pie',
    radius: ['55%', '78%'],
    label: { show: false },
    data: statusSegments.value.map(segment => ({
      name: segment.label,
      value: segment.value,
      itemStyle: { color: segment.color }
    }))
  }]
}))

function formatDuration(minutes: number) {
  if (!minutes) return '0h'
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  const [hours, minutes] = value.split(':')
  const date = new Date(2000, 0, 1, Number(hours), Number(minutes))
  return new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit' }).format(date)
}

function moveMonth(delta: number) {
  monthCursor.value = new Date(monthCursor.value.getFullYear(), monthCursor.value.getMonth() + delta, 1)
}

function openCorrection(record: AttendanceRecord) {
  correctionRecord.value = record
  correction.requested_punch_in = record.punch_in?.slice(0, 5) || ''
  correction.requested_punch_out = record.punch_out?.slice(0, 5) || ''
  correction.reason = ''
}

async function submitCorrection() {
  if (!correctionRecord.value || correction.reason.trim().length < 5) return
  correctionLoading.value = true
  try {
    await api.request<AttendanceCorrection>('attendance/corrections', {
      method: 'POST',
      body: {
        attendance_record_id: correctionRecord.value.id,
        requested_punch_in: correction.requested_punch_in || null,
        requested_punch_out: correction.requested_punch_out || null,
        reason: correction.reason.trim()
      }
    })
    toast.add({ title: 'Correction request submitted', description: 'Your approver can now review the request.', color: 'success', icon: 'i-lucide-circle-check' })
    correctionRecord.value = null
    await refresh()
  } catch (requestError) {
    const candidate = requestError as { data?: { statusMessage?: string } }
    toast.add({ title: 'Could not submit correction', description: candidate.data?.statusMessage || 'Please review the details and try again.', color: 'error' })
  } finally {
    correctionLoading.value = false
  }
}

function hasPendingCorrection(recordId: number) {
  return attendanceData.value?.corrections.some(item => item.attendance_record_id === recordId && item.status === 'PENDING')
}
</script>

<template>
  <div>
    <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p class="text-sm font-medium text-primary">
          My workday
        </p>
        <h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Attendance
        </h2>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Review ERP-synced attendance and flag anything that needs correction.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <UButton
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="soft"
          aria-label="Previous month"
          @click="moveMonth(-1)"
        />
        <span class="min-w-36 text-center text-sm font-semibold">{{ monthLabel }}</span>
        <UButton
          icon="i-lucide-chevron-right"
          color="neutral"
          variant="soft"
          aria-label="Next month"
          @click="moveMonth(1)"
        />
      </div>
    </div>

    <UAlert
      v-if="auth.user.value?.is_superuser"
      class="mt-6"
      color="info"
      variant="soft"
      icon="i-lucide-shield-check"
      title="Technical account"
      description="This account is not an employee and does not have attendance records. Use System administration for technical account and integration settings."
    />
    <UAlert
      v-else-if="!employeeId"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-user-round-x"
      title="No employee profile is linked"
      description="Ask your People administrator to link this user account to an employee record before using attendance."
    />
    <UAlert
      v-else-if="error"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-coffee"
      title="Your attendance is taking a short break"
      description="We couldn’t refresh your attendance right now. Please try again in a moment."
      :actions="[{ label: 'Refresh attendance', onClick: () => refresh() }]"
    />

    <template v-if="employeeId">
      <div class="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="card in summaryCards"
          :key="card.label"
          class="people-card p-5"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm font-medium text-muted">
                {{ card.label }}
              </p><USkeleton
                v-if="pending"
                class="mt-3 h-8 w-20"
              /><p
                v-else
                class="mt-2 text-2xl font-semibold tabular-nums"
              >
                {{ card.value }}
              </p><p class="mt-1 text-xs text-muted">
                {{ card.note }}
              </p>
            </div>
            <span
              class="grid size-10 place-items-center rounded-xl"
              :style="{ background: card.tone }"
            ><UIcon
              :name="card.icon"
              class="size-5"
            /></span>
          </div>
        </div>
      </div>

      <div class="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <UCard>
          <template #header>
            <div>
              <h3 class="font-semibold">
                Attendance breakdown
              </h3>
              <p class="mt-1 text-sm text-muted">
                Status distribution for {{ monthLabel }}
              </p>
            </div>
          </template>
          <div class="flex flex-col items-center gap-6 sm:flex-row sm:justify-center">
            <ClientOnly>
              <VChart
                class="h-52 w-full shrink-0 sm:w-56"
                :option="attendanceChartOption"
                autoresize
                aria-label="Attendance status distribution chart"
              />
              <template #fallback>
                <USkeleton class="h-52 w-full sm:w-56" />
              </template>
            </ClientOnly>
            <div class="grid w-full gap-3 sm:max-w-xs">
              <p class="text-sm text-muted">
                <span class="font-semibold tabular-nums text-default">{{ chartTotal }}</span> recorded days
              </p>
              <div
                v-for="segment in statusSegments"
                :key="segment.label"
                class="flex items-center justify-between gap-4 text-sm"
              >
                <span class="flex items-center gap-2"><span
                  class="size-2.5 rounded-full"
                  :style="{ backgroundColor: segment.color }"
                />{{ segment.label }}</span>
                <span class="font-semibold tabular-nums">{{ segment.value }}</span>
              </div>
            </div>
          </div>
        </UCard>
      </div>

      <section class="people-card mt-6 overflow-hidden">
        <div class="flex flex-col gap-3 border-b border-[var(--people-border)] p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <h3 class="font-semibold">
              Monthly calendar
            </h3><p class="mt-1 text-sm text-muted">
              Your processed attendance for {{ monthLabel }}
            </p>
          </div>
          <div class="flex flex-wrap gap-2 text-xs text-muted">
            <span class="flex items-center gap-1.5"><i class="size-2 rounded-full bg-emerald-500" />Present</span><span class="flex items-center gap-1.5"><i class="size-2 rounded-full bg-rose-500" />Absent</span><span class="flex items-center gap-1.5"><i class="size-2 rounded-full bg-violet-500" />Leave</span><span class="flex items-center gap-1.5"><i class="size-2 rounded-full bg-amber-500" />Attention</span>
          </div>
        </div>

        <div class="hidden lg:block">
          <div class="grid grid-cols-7 border-b border-[var(--people-border)] bg-muted/5 text-center text-xs font-semibold uppercase tracking-wide text-muted">
            <div
              v-for="day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']"
              :key="day"
              class="px-3 py-3"
            >
              {{ day }}
            </div>
          </div>
          <div class="grid grid-cols-7">
            <div
              v-for="day in calendarDays"
              :key="day.key"
              class="min-h-32 border-b border-r border-[var(--people-border)] p-3"
              :class="day.currentMonth ? '' : 'bg-muted/5 opacity-45'"
            >
              <div class="flex items-center justify-between">
                <span class="text-sm font-semibold tabular-nums">{{ day.date.getDate() }}</span><span
                  v-if="day.key === dateKey(new Date())"
                  class="rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold text-white"
                >Today</span>
              </div>
              <div
                v-if="day.record"
                class="mt-3"
              >
                <AttendanceStatusBadge :status="day.record.status" />
                <p class="mt-3 text-xs font-medium tabular-nums">
                  {{ formatTime(day.record.punch_in) }} – {{ formatTime(day.record.punch_out) }}
                </p>
                <button
                  v-if="['MISSED_PUNCH', 'ABSENT'].includes(day.record.status) && !hasPendingCorrection(day.record.id)"
                  type="button"
                  class="mt-2 text-xs font-semibold text-primary hover:underline"
                  @click="openCorrection(day.record)"
                >
                  Request correction
                </button>
                <span
                  v-else-if="hasPendingCorrection(day.record.id)"
                  class="mt-2 inline-flex text-xs font-medium text-amber-700 dark:text-amber-300"
                >Correction pending</span>
              </div>
            </div>
          </div>
        </div>

        <div class="divide-y divide-[var(--people-border)] lg:hidden">
          <div
            v-if="!pending && !records.length"
            class="p-10 text-center"
          >
            <UIcon
              name="i-lucide-calendar-search"
              class="mx-auto size-8 text-muted"
            /><p class="mt-3 text-sm font-semibold">
              No attendance records
            </p><p class="mt-1 text-xs text-muted">
              There are no processed records for this month yet.
            </p>
          </div>
          <div
            v-for="record in records"
            :key="record.id"
            class="p-4 sm:p-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm font-semibold">
                  {{ new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(`${record.attendance_date}T00:00:00`)) }}
                </p><p class="mt-2 text-xs text-muted tabular-nums">
                  {{ formatTime(record.punch_in) }} – {{ formatTime(record.punch_out) }} · {{ formatDuration(record.worked_minutes) }}
                </p>
              </div>
              <AttendanceStatusBadge :status="record.status" />
            </div>
            <div
              v-if="record.late_minutes || record.early_exit_minutes || ['MISSED_PUNCH', 'ABSENT'].includes(record.status)"
              class="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted"
            >
              <span v-if="record.late_minutes">{{ record.late_minutes }}m late</span><span v-if="record.early_exit_minutes">{{ record.early_exit_minutes }}m early exit</span>
              <button
                v-if="!hasPendingCorrection(record.id)"
                type="button"
                class="font-semibold text-primary"
                @click="openCorrection(record)"
              >
                Request correction
              </button><span
                v-else
                class="font-medium text-amber-700 dark:text-amber-300"
              >Correction pending</span>
            </div>
          </div>
        </div>
      </section>
    </template>

    <div
      v-if="correctionRecord"
      class="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-6"
      @click.self="correctionRecord = null"
    >
      <section class="w-full max-w-lg rounded-t-3xl bg-[var(--people-surface)] p-6 shadow-2xl sm:rounded-2xl sm:p-7">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-semibold text-primary">
              Attendance correction
            </p><h3 class="mt-1 text-xl font-semibold">
              Fix {{ new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'long' }).format(new Date(`${correctionRecord.attendance_date}T00:00:00`)) }}
            </h3>
          </div><UButton
            icon="i-lucide-x"
            color="neutral"
            variant="ghost"
            aria-label="Close"
            @click="correctionRecord = null"
          />
        </div>
        <div class="mt-6 grid gap-4 sm:grid-cols-2">
          <UFormField label="Correct punch in">
            <UInput
              v-model="correction.requested_punch_in"
              class="w-full"
              type="time"
              size="lg"
            />
          </UFormField><UFormField label="Correct punch out">
            <UInput
              v-model="correction.requested_punch_out"
              class="w-full"
              type="time"
              size="lg"
            />
          </UFormField>
        </div>
        <UFormField
          class="mt-4"
          label="Reason"
          help="Explain what happened so your approver has enough context."
          required
        >
          <UTextarea
            v-model="correction.reason"
            class="w-full"
            :rows="4"
            placeholder="For example: I forgot to check out after the client meeting."
          />
        </UFormField>
        <UAlert
          v-if="correction.reason && correction.reason.trim().length < 5"
          class="mt-4"
          color="warning"
          variant="soft"
          description="Please add a little more detail."
        />
        <div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <UButton
            color="neutral"
            variant="soft"
            @click="correctionRecord = null"
          >
            Cancel
          </UButton><UButton
            icon="i-lucide-send"
            :loading="correctionLoading"
            :disabled="correction.reason.trim().length < 5"
            @click="submitCorrection"
          >
            Submit request
          </UButton>
        </div>
      </section>
    </div>
  </div>
</template>
