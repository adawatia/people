<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
import type { LeaveApplication, LeaveBalance, LeaveType } from '#shared/types/leave'

useSeoMeta({ title: 'Leave' })
const auth = useAuth()
const api = useHrmsApi()
const toast = useToast()
const employeeId = computed(() => auth.user.value?.employee_id)
const applyOpen = ref(false)
const submitting = ref(false)
const cancellingId = ref<number | null>(null)
const filter = ref('ALL')
const today = new Date().toISOString().slice(0, 10)
const form = reactive({ leave_type_id: 0, from_date: today, to_date: today, half_day: false, reason: '' })

const { data, pending, error, refresh } = await useAsyncData('my-leave', async () => {
  if (!employeeId.value) return null
  const [balances, applications, types] = await Promise.all([
    api.request<LeaveBalance[]>(`leaves/balance/employee/${employeeId.value}`),
    api.request<LeaveApplication[]>('leaves/', { query: { employee_id: employeeId.value } }),
    api.request<LeaveType[]>('leaves/types', { query: { is_active: true } })
  ])
  return { balances, applications, types }
}, { watch: [employeeId] })

const filteredApplications = computed(() => (data.value?.applications || []).filter(item => filter.value === 'ALL' || item.status === filter.value))
const pendingDaysByType = computed(() => {
  const totals = new Map<number, number>()
  for (const application of data.value?.applications || []) {
    if (application.status === 'PENDING') {
      totals.set(application.leave_type_id, (totals.get(application.leave_type_id) || 0) + application.days_count)
    }
  }
  return totals
})
function displayPending(balance: LeaveBalance) {
  return pendingDaysByType.value.get(balance.leave_type_id) ?? balance.pending
}
function displayAvailable(balance: LeaveBalance) {
  return Math.max(0, balance.allocated - balance.used - displayPending(balance))
}
function balanceIsSyncing(balance: LeaveBalance) {
  return displayPending(balance) !== balance.pending
}
const selectedBalance = computed(() => data.value?.balances.find(item => item.leave_type_id === form.leave_type_id))
const estimatedDays = computed(() => {
  const from = new Date(`${form.from_date}T00:00:00`)
  const to = new Date(`${form.to_date}T00:00:00`)
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to < from) return 0
  return form.half_day ? 0.5 : Math.floor((to.getTime() - from.getTime()) / 86400000) + 1
})
const formValid = computed(() => form.leave_type_id > 0 && estimatedDays.value > 0 && form.reason.trim().length >= 3)

function openApplication() {
  const first = data.value?.balances.find(item => item.available > 0) || data.value?.balances[0]
  form.leave_type_id = first?.leave_type_id || data.value?.types[0]?.id || 0
  form.from_date = today
  form.to_date = today
  form.half_day = false
  form.reason = ''
  applyOpen.value = true
}

function statusConfig(status: string) {
  const values: Record<string, { color: 'warning' | 'success' | 'error' | 'neutral', icon: string }> = {
    PENDING: { color: 'warning', icon: 'i-lucide-clock-3' },
    CANCELLATION_PENDING: { color: 'warning', icon: 'i-lucide-rotate-ccw' },
    APPROVED: { color: 'success', icon: 'i-lucide-circle-check' },
    REJECTED: { color: 'error', icon: 'i-lucide-circle-x' },
    CANCELLED: { color: 'neutral', icon: 'i-lucide-ban' }
  }
  return values[status] || values.CANCELLED!
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${value}T00:00:00`))
}

async function submitApplication() {
  if (!employeeId.value || !formValid.value) return
  submitting.value = true
  try {
    await api.request<LeaveApplication>('leaves/', {
      method: 'POST',
      body: {
        employee_id: employeeId.value,
        leave_type_id: form.leave_type_id,
        from_date: form.from_date,
        to_date: form.half_day ? form.from_date : form.to_date,
        half_day: form.half_day,
        half_day_date: form.half_day ? form.from_date : null,
        reason: form.reason.trim()
      }
    })
    applyOpen.value = false
    toast.add({ title: 'Leave request submitted', description: 'You can track its status here.', color: 'success', icon: 'i-lucide-circle-check' })
    await refresh()
  } catch (submitError) {
    const candidate = submitError as { data?: { statusMessage?: string } }
    toast.add({ title: 'Could not submit leave', description: candidate.data?.statusMessage || 'Check the selected dates and your balance.', color: 'error' })
  } finally {
    submitting.value = false
  }
}

async function cancelApplication(application: LeaveApplication) {
  const leaveHasStarted = application.status === 'APPROVED' && application.from_date <= today && today <= application.to_date
  let body: { effective_date?: string, reason?: string } | undefined
  if (leaveHasStarted) {
    const reason = prompt('Why are you returning from leave today? This will be sent to your approver.')
    if (!reason || reason.trim().length < 3) return
    body = { effective_date: today, reason: reason.trim() }
  } else if (!confirm(`Cancel your ${application.leave_type_name || 'leave'} request?`)) return
  cancellingId.value = application.id
  try {
    await api.request(`leaves/${application.id}/cancel`, { method: 'PATCH', body })
    toast.add({
      title: leaveHasStarted ? 'Early-return request submitted' : 'Leave request cancelled',
      description: leaveHasStarted ? 'Your approver must confirm the unused leave days.' : undefined,
      color: 'neutral',
      icon: leaveHasStarted ? 'i-lucide-clock-3' : 'i-lucide-ban'
    })
    await refresh()
  } catch (cancelError) {
    const candidate = cancelError as { data?: { statusMessage?: string } }
    toast.add({ title: 'Could not cancel request', description: candidate.data?.statusMessage || 'Please try again.', color: 'error' })
  } finally {
    cancellingId.value = null
  }
}
</script>

<template>
  <div>
    <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p class="text-sm font-medium text-primary">
          Time away
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Leave
        </h2><p class="mt-2 max-w-2xl text-sm leading-6 text-muted">
          See your available balance, request time off, and follow every approval.
        </p>
      </div>
      <UButton
        size="lg"
        icon="i-lucide-plus"
        :disabled="!employeeId || !data?.types.length"
        @click="openApplication"
      >
        Request leave
      </UButton>
    </div>

    <UAlert
      v-if="!employeeId"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-user-round-x"
      title="No employee profile is linked"
      description="Ask your People administrator to link this account before requesting leave."
    />
    <UAlert
      v-else-if="error"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-coffee"
      title="Your leave board is taking a short break"
      description="We couldn’t refresh your leave details just now. Your requests are safe — please try again in a moment."
      :actions="[{ label: 'Refresh leave board', onClick: () => refresh() }]"
    />

    <template v-if="employeeId">
      <section class="mt-7">
        <div class="mb-4 flex items-center justify-between">
          <div>
            <h3 class="font-semibold">
              Your balances
            </h3><p class="mt-1 text-sm text-muted">
              Available days in the current leave period
            </p>
          </div>
        </div>
        <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <template v-if="pending">
            <div
              v-for="index in 4"
              :key="index"
              class="people-card p-5"
            >
              <USkeleton class="h-4 w-28" /><USkeleton class="mt-5 h-10 w-20" /><USkeleton class="mt-5 h-2 w-full" />
            </div>
          </template>
          <article
            v-for="(balance, index) in data?.balances"
            v-else
            :key="balance.leave_type_id"
            class="people-card p-5"
          >
            <div class="flex items-start justify-between">
              <div>
                <p class="font-semibold">
                  {{ balance.leave_type_name }}
                </p><p class="mt-1 text-xs font-semibold uppercase tracking-wide text-muted">
                  {{ balance.leave_type_code }}
                </p>
              </div><span
                class="grid size-10 place-items-center rounded-xl"
                :style="{ background: ['var(--people-lavender)', 'var(--people-mint)', 'var(--people-blue)', 'var(--people-peach)'][index % 4] }"
              ><UIcon
                name="i-lucide-calendar-heart"
                class="size-5"
              /></span>
            </div>
            <div class="mt-5 flex items-end gap-2">
              <span class="text-3xl font-semibold tabular-nums">{{ displayAvailable(balance) }}</span><span class="pb-1 text-sm text-muted">days available</span>
            </div>
            <div class="mt-4 h-2 overflow-hidden rounded-full bg-muted/10">
              <div
                class="h-full rounded-full bg-primary transition-all"
                :style="{ width: `${Math.min(100, balance.allocated ? (displayAvailable(balance) / balance.allocated) * 100 : 0)}%` }"
              />
            </div>
            <div class="mt-3 flex justify-between text-xs text-muted">
              <span>{{ balance.used }} used</span><span>{{ displayPending(balance) }} pending</span><span>{{ balance.allocated }} allocated</span>
            </div>
            <p
              v-if="balanceIsSyncing(balance)"
              class="mt-3 flex items-center gap-1.5 text-xs text-primary"
            >
              <UIcon
                name="i-lucide-refresh-cw"
                class="size-3.5"
              />
              Official balance is syncing with ERP
            </p>
          </article>
        </div>
        <div
          v-if="!pending && data && !data.balances.length"
          class="people-card mt-4 flex flex-col items-center p-8 text-center"
        >
          <span
            class="grid size-12 place-items-center rounded-2xl bg-[var(--people-lavender)] text-primary"
          >
            <UIcon
              name="i-lucide-sparkles"
              class="size-6"
            />
          </span>
          <h4 class="mt-4 font-semibold">
            Your leave balance is on its way
          </h4>
          <p class="mt-1 max-w-md text-sm leading-6 text-muted">
            We’re waiting for this year’s balance from your People system. Once it arrives, it will appear here automatically.
          </p>
        </div>
      </section>

      <section class="people-card mt-7 overflow-hidden">
        <div class="flex flex-col gap-4 border-b border-[var(--people-border)] p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <h3 class="font-semibold">
              Leave history
            </h3><p class="mt-1 text-sm text-muted">
              Your recent requests and decisions
            </p>
          </div>
          <div class="flex gap-1 overflow-x-auto rounded-xl bg-muted/5 p-1">
            <button
              v-for="option in ['ALL', 'PENDING', 'APPROVED', 'REJECTED']"
              :key="option"
              type="button"
              class="rounded-lg px-3 py-2 text-xs font-semibold transition-colors"
              :class="filter === option ? 'bg-[var(--people-surface)] text-highlighted shadow-sm' : 'text-muted'"
              @click="filter = option"
            >
              {{ option === 'ALL' ? 'All' : option.charAt(0) + option.slice(1).toLowerCase() }}
            </button>
          </div>
        </div>

        <div class="hidden overflow-x-auto md:block">
          <table class="w-full min-w-[760px] text-left text-sm">
            <thead class="bg-muted/5 text-xs uppercase tracking-wide text-muted">
              <tr>
                <th class="px-6 py-3 font-semibold">
                  Leave type
                </th><th class="px-4 py-3 font-semibold">
                  Dates
                </th><th class="px-4 py-3 font-semibold">
                  Days
                </th><th class="px-4 py-3 font-semibold">
                  Status
                </th><th class="px-4 py-3 font-semibold">
                  Reason
                </th><th class="px-6 py-3 text-right font-semibold">
                  Action
                </th>
              </tr>
            </thead><tbody class="divide-y divide-[var(--people-border)]">
              <tr
                v-for="application in filteredApplications"
                :key="application.id"
              >
                <td class="px-6 py-4 font-semibold">
                  {{ application.leave_type_name || `Leave #${application.leave_type_id}` }}
                </td><td class="px-4 py-4 tabular-nums">
                  {{ formatDate(application.from_date) }}<span v-if="application.to_date !== application.from_date"> – {{ formatDate(application.to_date) }}</span>
                </td><td class="px-4 py-4 tabular-nums">
                  {{ application.days_count }}
                </td><td class="px-4 py-4">
                  <UBadge
                    :label="application.status.charAt(0) + application.status.slice(1).toLowerCase()"
                    :color="statusConfig(application.status).color"
                    variant="soft"
                    :icon="statusConfig(application.status).icon"
                  />
                </td><td class="max-w-64 truncate px-4 py-4 text-muted">
                  {{ application.reason || '—' }}
                </td><td class="px-6 py-4 text-right">
                  <UButton
                    v-if="application.status === 'PENDING' || (application.status === 'APPROVED' && application.to_date >= today)"
                    size="sm"
                    color="neutral"
                    variant="ghost"
                    :loading="cancellingId === application.id"
                    @click="cancelApplication(application)"
                  >
                    {{ application.status === 'APPROVED' && application.from_date <= today ? 'Request early return' : 'Cancel' }}
                  </UButton>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="divide-y divide-[var(--people-border)] md:hidden">
          <article
            v-for="application in filteredApplications"
            :key="application.id"
            class="p-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="font-semibold">
                  {{ application.leave_type_name || `Leave #${application.leave_type_id}` }}
                </p><p class="mt-1 text-xs text-muted">
                  {{ formatDate(application.from_date) }}<span v-if="application.to_date !== application.from_date"> – {{ formatDate(application.to_date) }}</span> · {{ application.days_count }} day{{ application.days_count === 1 ? '' : 's' }}
                </p>
              </div><UBadge
                :label="application.status.charAt(0) + application.status.slice(1).toLowerCase()"
                :color="statusConfig(application.status).color"
                variant="soft"
              />
            </div><p
              v-if="application.reason"
              class="mt-3 text-sm leading-6 text-muted"
            >
              {{ application.reason }}
            </p><p
              v-if="application.rejection_reason"
              class="mt-3 rounded-xl bg-rose-50 p-3 text-xs leading-5 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200"
            >
              {{ application.rejection_reason }}
            </p><UButton
              v-if="application.status === 'PENDING' || (application.status === 'APPROVED' && application.to_date >= today)"
              class="mt-3"
              size="sm"
              color="neutral"
              variant="soft"
              :loading="cancellingId === application.id"
              @click="cancelApplication(application)"
            >
              {{ application.status === 'APPROVED' && application.from_date <= today ? 'Request early return' : 'Cancel request' }}
            </UButton>
          </article>
        </div>

        <div
          v-if="!pending && !filteredApplications.length && !data?.applications.length"
          class="px-6 py-14 text-center"
        >
          <UIcon
            name="i-lucide-sparkles"
            class="mx-auto size-9 text-primary"
          /><p class="mt-3 text-sm font-semibold">
            No leave plans yet
          </p><p class="mx-auto mt-1 max-w-sm text-xs leading-5 text-muted">
            You haven’t applied for any leave. When you need a little time away, your request will show up here.
          </p><UButton
            class="mt-5"
            icon="i-lucide-plus"
            :disabled="!data?.types.length"
            @click="openApplication"
          >
            Request your first leave
          </UButton>
        </div>
        <div
          v-else-if="!pending && !filteredApplications.length"
          class="px-6 py-14 text-center"
        >
          <UIcon
            name="i-lucide-filter-x"
            class="mx-auto size-9 text-muted"
          /><p class="mt-3 text-sm font-semibold">
            Nothing in this filter
          </p><p class="mt-1 text-xs text-muted">
            Try another status to see more of your leave history.
          </p>
        </div>
      </section>
    </template>

    <div
      v-if="applyOpen"
      class="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/40 backdrop-blur-[2px] sm:items-center sm:p-6"
      @click.self="applyOpen = false"
    >
      <section class="max-h-[94dvh] w-full overflow-y-auto rounded-t-3xl bg-[var(--people-surface)] p-5 shadow-2xl sm:max-w-2xl sm:rounded-2xl sm:p-7">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-semibold text-primary">
              New request
            </p><h3 class="mt-1 text-2xl font-semibold">
              Request leave
            </h3><p class="mt-2 text-sm text-muted">
              The final day count is calculated by the leave policy.
            </p>
          </div><UButton
            icon="i-lucide-x"
            color="neutral"
            variant="ghost"
            aria-label="Close"
            @click="applyOpen = false"
          />
        </div>
        <div class="mt-6 grid gap-5 sm:grid-cols-2">
          <UFormField
            class="sm:col-span-2"
            label="Leave type"
            required
          >
            <select
              v-model.number="form.leave_type_id"
              class="h-12 w-full rounded-lg border border-[var(--people-border)] bg-[var(--people-surface)] px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            >
              <option
                v-for="type in data?.types"
                :key="type.id"
                :value="type.id"
              >
                {{ type.name }} ({{ type.code }})
              </option>
            </select>
          </UFormField>
          <UFormField
            label="From"
            required
          >
            <UInput
              v-model="form.from_date"
              class="w-full"
              type="date"
              size="xl"
              :min="today"
            />
          </UFormField>
          <UFormField
            label="To"
            required
          >
            <UInput
              v-model="form.to_date"
              class="w-full"
              type="date"
              size="xl"
              :min="form.from_date"
              :disabled="form.half_day"
            />
          </UFormField>
          <label class="sm:col-span-2 flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--people-border)] p-4"><UCheckbox v-model="form.half_day" /><span><span class="block text-sm font-semibold">Half-day leave</span><span class="mt-1 block text-xs text-muted">The start date will be used as the half-day date.</span></span></label>
          <UFormField
            class="sm:col-span-2"
            label="Reason"
            required
          >
            <UTextarea
              v-model="form.reason"
              class="w-full"
              :rows="4"
              placeholder="Give your approver enough context."
            />
          </UFormField>
        </div>
        <div class="mt-5 grid gap-3 rounded-2xl bg-[var(--people-lavender)] p-4 text-sm sm:grid-cols-3">
          <div>
            <p class="text-xs font-medium text-muted">
              Estimated request
            </p><p class="mt-1 font-semibold">
              {{ estimatedDays }} day{{ estimatedDays === 1 ? '' : 's' }}
            </p>
          </div><div>
            <p class="text-xs font-medium text-muted">
              Available now
            </p><p class="mt-1 font-semibold">
              {{ selectedBalance?.available ?? 0 }} days
            </p>
          </div><div>
            <p class="text-xs font-medium text-muted">
              After approval
            </p><p class="mt-1 font-semibold">
              {{ Math.max(0, (selectedBalance?.available || 0) - estimatedDays) }} days
            </p>
          </div>
        </div>
        <UAlert
          v-if="estimatedDays > (selectedBalance?.available || 0)"
          class="mt-4"
          color="warning"
          variant="soft"
          icon="i-lucide-triangle-alert"
          description="This estimate exceeds your currently available balance. The server will validate the exact policy-adjusted duration."
        />
        <div class="sticky bottom-0 -mx-5 mt-6 flex flex-col-reverse gap-3 border-t border-[var(--people-border)] bg-[var(--people-surface)] px-5 pt-4 sm:static sm:mx-0 sm:flex-row sm:justify-end sm:border-0 sm:p-0">
          <UButton
            color="neutral"
            variant="soft"
            @click="applyOpen = false"
          >
            Cancel
          </UButton><UButton
            icon="i-lucide-send"
            :loading="submitting"
            :disabled="!formValid"
            @click="submitApplication"
          >
            Submit request
          </UButton>
        </div>
      </section>
    </div>
  </div>
</template>
