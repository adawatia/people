<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes, @stylistic/max-statements-per-line */
import type { AttendanceMatrix, LeaveSummary } from '#shared/types/report'

useSeoMeta({ title: 'Reports' })
const api = useHrmsApi(); const auth = useAuth(); const tab = ref<'attendance' | 'leave'>(auth.hasPermission('reports.attendance') ? 'attendance' : 'leave'); const month = ref(new Date().toISOString().slice(0, 7)); const year = ref(new Date().getFullYear())
const { data, pending, error, refresh } = await useAsyncData('reports', async () => { if (tab.value === 'attendance') { const [y, m] = month.value.split('-').map(Number); return { attendance: await api.request<AttendanceMatrix>('reports/attendance-matrix', { query: { year: y, month: m } }), leave: null } } return { attendance: null, leave: await api.request<LeaveSummary>('reports/leave-summary', { query: { year: year.value } }) } }, { watch: [tab, month, year] })
const days = computed(() => Array.from({ length: data.value?.attendance?.total_days_in_month || 0 }, (_, index) => index + 1))
const statusClass = (value?: string) => ({ P: 'bg-emerald-100 text-emerald-800', A: 'bg-rose-100 text-rose-800', L: 'bg-violet-100 text-violet-800', HD: 'bg-amber-100 text-amber-800', WFH: 'bg-sky-100 text-sky-800', WO: 'bg-slate-100 text-slate-600', H: 'bg-orange-100 text-orange-800' }[value || ''] || 'text-muted')
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Analytics
        </p><h2 class="mt-1 text-2xl font-semibold sm:text-3xl">
          Reports
        </h2><p class="mt-2 text-sm text-muted">
          Inspect monthly attendance and annual leave balances.
        </p>
      </div><UInput
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
    </div><div class="mt-7 flex gap-2 border-b border-[var(--people-border)]">
      <button
        v-if="auth.hasPermission('reports.attendance')"
        class="min-h-11 border-b-2 px-3 text-sm font-semibold"
        :class="tab === 'attendance' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        @click="tab = 'attendance'"
      >
        Attendance matrix
      </button><button
        v-if="auth.hasPermission('reports.leave')"
        class="min-h-11 border-b-2 px-3 text-sm font-semibold"
        :class="tab === 'leave' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        @click="tab = 'leave'"
      >
        Leave summary
      </button>
    </div><UAlert
      v-if="error"
      class="mt-5"
      color="error"
      variant="soft"
      title="Report is unavailable"
      :actions="[{ label: 'Try again', onClick: () => refresh() }]"
    /><div
      v-else-if="pending"
      class="people-card mt-5 p-5"
    >
      <USkeleton class="h-96" />
    </div><section
      v-else-if="tab === 'attendance'"
      class="people-card mt-5 overflow-hidden"
    >
      <div class="overflow-x-auto">
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
              v-for="row in data?.attendance?.rows"
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
      v-else
      class="people-card mt-5 overflow-hidden"
    >
      <div class="hidden overflow-x-auto sm:block">
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
              v-for="row in data?.leave?.rows"
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
      </div><div class="divide-y divide-[var(--people-border)] sm:hidden">
        <article
          v-for="row in data?.leave?.rows"
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
  </div>
</template>
