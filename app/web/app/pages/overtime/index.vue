<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
import type { OvertimeRecord, OvertimeSummary } from '#shared/types/overtime'

useSeoMeta({ title: 'Overtime' })
const auth = useAuth()
const api = useHrmsApi()
const employeeId = computed(() => auth.user.value?.employee_id)
const selectedMonth = ref(new Date().toISOString().slice(0, 7))
const statusFilter = ref('ALL')
const { data, pending, error, refresh } = await useAsyncData('my-overtime', async () => {
  if (!employeeId.value) return null
  const parts = selectedMonth.value.split('-').map(Number)
  const [summary, records] = await Promise.all([
    api.request<OvertimeSummary>(`overtime/employee/${employeeId.value}/summary`, { query: { year: parts[0], month: parts[1] } }),
    api.request<OvertimeRecord[]>('overtime/', { query: { employee_id: employeeId.value } })
  ])
  return { summary, records }
}, { watch: [employeeId, selectedMonth] })
const filtered = computed(() => (data.value?.records || []).filter(item => statusFilter.value === 'ALL' || item.status === statusFilter.value))
const hours = (minutes: number) => `${Math.floor(minutes / 60)}h ${minutes % 60}m`
const statusColor = (value: string) => ({ PENDING: 'warning', APPROVED: 'success', REJECTED: 'error' }[value] || 'neutral') as 'warning' | 'success' | 'error' | 'neutral'
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Time tracking
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          My overtime
        </h2><p class="mt-2 text-sm text-muted">
          Review calculated hours and approval status.
        </p>
      </div>
      <UInput
        v-model="selectedMonth"
        type="month"
        icon="i-lucide-calendar-range"
        class="w-full sm:w-48"
      />
    </div>
    <UAlert
      v-if="!employeeId"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-user-round-x"
      title="No employee profile is linked"
    />
    <UAlert
      v-else-if="error"
      class="mt-6"
      color="error"
      variant="soft"
      icon="i-lucide-cloud-off"
      title="Overtime information is unavailable"
      :actions="[{ label: 'Try again', onClick: () => refresh() }]"
    />
    <template v-else-if="employeeId">
      <section class="mt-7 grid gap-4 sm:grid-cols-3">
        <article
          v-for="metric in [{ label: 'Calculated', value: hours(data?.summary.total_calculated_minutes || 0), icon: 'i-lucide-timer', bg: 'var(--people-blue)' }, { label: 'Approved', value: hours(data?.summary.total_approved_minutes || 0), icon: 'i-lucide-circle-check', bg: 'var(--people-mint)' }, { label: 'Pending reviews', value: String(data?.summary.pending_count || 0), icon: 'i-lucide-hourglass', bg: 'var(--people-peach)' }]"
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
      <section class="people-card mt-7 overflow-hidden">
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
                Attendance record #{{ item.attendance_record_id }}
              </p><p class="mt-1 text-xs text-muted">
                Overtime reference #{{ item.id }}
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
      </section>
    </template>
  </div>
</template>
