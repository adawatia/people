<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { LeaveApplication, LeaveBalance, LeaveType } from '#shared/types/leave'

useSeoMeta({ title: 'Leave' })
const auth = useAuth()
const workspace = useWorkspace()
const api = useHrmsApi()
const toast = useToast()
const employeeId = computed(() => auth.user.value?.employee_id)
const managementMode = computed(() => workspace.current.value === 'TEAM' || workspace.current.value === 'HR')
const applyOpen = ref(false)
const submitting = ref(false)
const cancellingId = ref<number | null>(null)
const list = useListState({ status: 'ALL', sort_order: 'desc' })
const filter = list.field('status')
const today = new Date().toISOString().slice(0, 10)
const form = reactive({ leave_type_id: 0, from_date: today, to_date: today, half_day: false, reason: '' })

const { data: rawData, pending, error, refresh } = await useAsyncData('my-leave', async (_app, { signal }) => {
  if (!managementMode.value && !employeeId.value) return null
  const balanceRequest = !managementMode.value && employeeId.value
    ? api.request<LeaveBalance[]>(`leaves/balance/employee/${employeeId.value}`)
    : Promise.resolve([])
  const applicationsRequest = api.request<PaginatedResponse<LeaveApplication>>('leaves/', {
    signal, query: { ...list.query.value, status: filter.value === 'ALL' ? undefined : filter.value, employee_id: managementMode.value ? undefined : employeeId.value }
  })
  const typesRequest = api.request<PaginatedResponse<LeaveType>>('leaves/types', { query: { is_active: true } })
  const [balances, applications, types] = await Promise.all([balanceRequest, applicationsRequest, typesRequest])
  return { balances, applications, types: types.items }
}, { watch: [employeeId, managementMode, list.query, filter] })
const data = useRetainedData(rawData)

const filteredApplications = computed(() => data.value?.applications.items || [])
function displayPending(balance: LeaveBalance) {
  return balance.pending
}
function displayAvailable(balance: LeaveBalance) {
  return balance.available
}
function balanceIsSyncing(_balance: LeaveBalance) {
  return false
}
const selectedBalance = computed(() => data.value?.balances.find(item => item.leave_type_id === form.leave_type_id))
const estimatedDays = computed(() => {
  const from = new Date(`${form.from_date}T00:00:00`)
  const to = new Date(`${form.to_date}T00:00:00`)
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to < from) return 0
  return form.half_day ? 0.5 : Math.floor((to.getTime() - from.getTime()) / 86400000) + 1
})
const formValid = computed(() => form.leave_type_id > 0 && estimatedDays.value > 0 && form.reason.trim().length >= 3)

watch(managementMode, () => {
  applyOpen.value = false
  filter.value = 'ALL'
})

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
  if (submitting.value) return
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

const cancelTarget = ref<LeaveApplication | null>(null)
const cancelReason = ref('')
function cancelApplication(application: LeaveApplication) {
  cancelReason.value = ''
  cancelTarget.value = application
}
async function confirmCancellation() {
  const application = cancelTarget.value
  if (!application) return
  const leaveHasStarted = application.status === 'APPROVED' && application.from_date <= today && today <= application.to_date
  let body: { effective_date?: string, reason?: string } | undefined
  if (leaveHasStarted) {
    if (cancelReason.value.trim().length < 3) return
    body = { effective_date: today, reason: cancelReason.value.trim() }
  }
  cancellingId.value = application.id
  try {
    await api.request(`leaves/${application.id}/cancel`, { method: 'PATCH', body })
    toast.add({
      title: leaveHasStarted ? 'Early-return request submitted' : 'Leave request cancelled',
      description: leaveHasStarted ? 'Your approver must confirm the unused leave days.' : undefined,
      color: 'neutral',
      icon: leaveHasStarted ? 'i-lucide-clock-3' : 'i-lucide-ban'
    })
    cancelTarget.value = null
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
  <div class="people-page">
    <DataFeedback
      :pending="pending"
      :error="error"
      :has-data="Boolean(data)"
    />
    <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          {{ managementMode ? 'Leave requests' : 'Leave' }}
        </h1><p class="mt-2 max-w-2xl text-sm leading-6 text-muted">
          {{ managementMode ? 'Review leave requests visible within your assigned scope.' : 'See your available balance, request time off, and follow every approval.' }}
        </p>
      </div>
      <UButton
        v-if="!managementMode"
        size="lg"
        icon="i-lucide-plus"
        :disabled="!employeeId || !data?.types.length"
        @click="openApplication"
      >
        Request leave
      </UButton>
    </div>

    <UAlert
      v-if="!managementMode && !employeeId"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-user-round-x"
      title="No employee profile is linked"
      description="Ask your People administrator to link this account before requesting leave."
    />
    <UAlert
      v-if="error"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-circle-alert"
      title="Updates could not be loaded"
      description="We couldn’t refresh your leave details just now. Your requests are safe — please try again in a moment."
      :actions="[{ label: 'Refresh leave board', onClick: () => refresh() }]"
    />

    <template v-if="employeeId && !managementMode">
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
        <div data-leave-balances class="grid sm:grid-cols-2 xl:grid-cols-4">
          <template v-if="pending && !data">
            <div
              v-for="index in 4"
              :key="index"
              class="people-card p-5"
            >
              <USkeleton class="h-4 w-28" /><USkeleton class="mt-5 h-10 w-20" /><USkeleton class="mt-5 h-2 w-full" />
            </div>
          </template>
          <article
            v-for="balance in data?.balances"
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
                :style="{ background: 'var(--people-lavender)', color: 'var(--people-lavender-ink)' }"
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
        </div>

        <ListControls
          v-model:search="list.search.value"
          v-model:sort-by="list.sortBy.value"
          v-model:sort-order="list.sortOrder.value"
          :active="list.active.value"
          :sorts="[{ label: 'Submitted', value: 'applied_at' }, { label: 'Status', value: 'status' }]"
          search-placeholder="Search leave requests"
          @clear="list.clear"
        >
          <template #quick>
            <UButton
              v-for="option in ['ALL', 'PENDING', 'APPROVED', 'REJECTED']"
              :key="option"
              size="sm"
              :variant="filter === option ? 'soft' : 'ghost'"
              :color="filter === option ? 'primary' : 'neutral'"
              :aria-pressed="filter === option"
              @click="filter = option"
            >
              {{ option === 'ALL' ? 'All statuses' : option.charAt(0) + option.slice(1).toLowerCase() }}
            </UButton>
          </template>
        </ListControls>

        <div
          class="hidden overflow-x-auto md:block"
          tabindex="0"
          aria-label="Scrollable comparison table"
        >
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
                </td><td class="max-w-64 break-words px-4 py-4 text-muted">
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
          v-if="!pending && !error && !list.active.value && !filteredApplications.length && !data?.applications.total"
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
        <ListEmptyState
          v-else-if="!pending && !error && !filteredApplications.length"
          title="No matching leave requests"
          :filtered="list.active.value"
          @reset="list.clear"
        />
      </section>
    </template>

    <section
      v-if="managementMode"
      class="people-card mt-7 overflow-hidden"
    >
      <div class="flex items-center justify-between border-b border-[var(--people-border)] p-5 sm:px-6">
        <div>
          <h3 class="font-semibold">
            Scoped leave requests
          </h3>
          <p class="mt-1 text-sm text-muted">
            Employees and requests are limited by your server-assigned scope.
          </p>
        </div>
        <UButton
          :to="workspace.link('/approvals')"
          icon="i-lucide-clipboard-check"
          color="neutral"
          variant="soft"
        >
          Open approvals
        </UButton>
      </div>
      <ListControls
        v-model:search="list.search.value"
        v-model:sort-by="list.sortBy.value"
        v-model:sort-order="list.sortOrder.value"
        :active="list.active.value"
        :sorts="[{ label: 'Submitted', value: 'applied_at' }, { label: 'Status', value: 'status' }]"
        search-placeholder="Search employee name or code"
        @clear="list.clear"
      >
        <template #quick>
          <UButton
            v-for="option in ['ALL', 'PENDING', 'APPROVED', 'REJECTED']"
            :key="option"
            size="sm"
            :variant="filter === option ? 'soft' : 'ghost'"
            :color="filter === option ? 'primary' : 'neutral'"
            :aria-pressed="filter === option"
            @click="filter = option"
          >
            {{ option === 'ALL' ? 'All statuses' : option.charAt(0) + option.slice(1).toLowerCase() }}
          </UButton>
        </template>
      </ListControls>
      <div
        v-if="pending && !data"
        class="space-y-3 p-5"
      >
        <USkeleton
          v-for="index in 5"
          :key="index"
          class="h-14 w-full"
        />
      </div>
      <UAlert
        v-if="error"
        class="m-5"
        color="warning"
        variant="soft"
        title="Requests could not be loaded"
        description="Refresh to try again."
        :actions="[{ label: 'Refresh', onClick: () => refresh() }]"
      />
      <div
        v-if="filteredApplications.length"
        class="divide-y divide-[var(--people-border)]"
      >
        <article
          v-for="application in filteredApplications"
          :key="application.id"
          class="flex flex-wrap items-center gap-3 p-5 sm:px-6"
        >
          <div class="min-w-0 flex-1">
            <p class="font-semibold">
              {{ application.employee_name || `Employee #${application.employee_id}` }} <span class="font-normal text-muted">· {{ application.leave_type_name || `Leave #${application.leave_type_id}` }}</span>
            </p>
            <p class="mt-1 text-sm text-muted">
              {{ formatDate(application.from_date) }}<span v-if="application.to_date !== application.from_date"> – {{ formatDate(application.to_date) }}</span> · {{ application.days_count }} day(s)
            </p>
          </div>
          <UBadge
            :label="application.status"
            :color="statusConfig(application.status).color"
            variant="soft"
          />
          <UButton
            v-if="['PENDING', 'CANCELLATION_PENDING'].includes(application.status)"
            :to="workspace.link('/approvals')"
            size="sm"
            color="neutral"
            variant="soft"
          >
            Review
          </UButton>
        </article>
      </div>
      <ListEmptyState
        v-else-if="!pending && !error"
        title="No requests found"
        description="Leave requests are shown within your assigned scope."
        :filtered="list.active.value"
        @reset="list.clear"
      />
    </section>

    <UModal
      v-model:open="applyOpen"
      title="Request leave"
      description="The final day count is calculated by the leave policy."
    >
      <template #body>
        <div class="mt-6 grid gap-5 sm:grid-cols-2">
          <UFormField
            class="sm:col-span-2"
            label="Leave type"
            required
          >
            <RemoteSelect
              v-model="form.leave_type_id"
              endpoint="leaves/types"
              label="Select leave type"
              :filters="{ is_active: true }"
            />
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
            :error="estimatedDays <= 0 ? 'Enter a valid date range with end on or after start.' : undefined"
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
            :error="form.reason && form.reason.trim().length < 3 ? 'Enter at least 3 characters.' : undefined"
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
            :disabled="submitting || !formValid"
            @click="submitApplication"
          >
            Submit request
          </UButton>
        </div>
      </template>
    </UModal>
    <ListPagination
      v-if="data?.applications"
      v-model:page="list.page.value"
      v-model:page-size="list.pageSize.value"
      :total="data?.applications?.total || 0"
      :total-pages="data?.applications?.total_pages"
      :loading="pending"
      label="requests"
    />
    <UModal
      :open="!!cancelTarget"
      title="Cancel request"
      description="Confirm cancellation. Approved leave that has started requires an early-return decision from your approver."
      @update:open="value => { if (!value && !cancellingId) cancelTarget = null }"
    >
      <template #body>
        <p class="text-sm text-muted">
          This changes the request status and may restore unused leave or remove the work arrangement.
        </p>
        <UFormField
          v-if="cancelTarget?.status === 'APPROVED' && cancelTarget.from_date <= today && today <= cancelTarget.to_date"
          label="Early-return reason"
          required
          class="mt-4"
        >
          <UTextarea
            v-model="cancelReason"
            class="w-full"
          />
        </UFormField>
      </template>
      <template #footer>
        <UButton
          color="neutral"
          variant="outline"
          :disabled="!!cancellingId"
          @click="cancelTarget = null"
        >
          Keep request
        </UButton>
        <UButton
          color="error"
          :loading="!!cancellingId"
          :disabled="!!cancellingId || (cancelTarget?.status === 'APPROVED' && cancelTarget.from_date <= today && today <= cancelTarget.to_date) && cancelReason.trim().length < 3"
          @click="confirmCancellation"
        >
          Confirm cancellation
        </UButton>
      </template>
    </UModal>
  </div>
</template>
