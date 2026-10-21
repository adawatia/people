<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { LeaveApplication } from '#shared/types/leave'
import type { WorkArrangement } from '#shared/types/work-arrangement'
import type { OvertimePage, OvertimeRecord } from '#shared/types/overtime'

type ApprovalTab = 'leave' | 'work' | 'overtime'

useSeoMeta({ title: 'Approvals' })
const api = useHrmsApi()
const auth = useAuth()
const toast = useToast()
const canLeave = computed(() => auth.hasPermission('leave.approve'))
const canRejectLeave = computed(() => auth.hasPermission('leave.reject'))
const canWork = computed(() => auth.hasPermission('work_arrangement.approve'))
const canOvertime = computed(() => auth.hasPermission('overtime.approve'))
const activeTab = ref<ApprovalTab>(canLeave.value ? 'leave' : canWork.value ? 'work' : 'overtime')
const actionKey = ref('')
const leaveReject = ref<LeaveApplication | null>(null)
const workReject = ref<WorkArrangement | null>(null)
const overtimeReject = ref<OvertimeRecord | null>(null)
const rejectionReason = ref('')
const leaveList = useListState({}, 'leave_')
const workList = useListState({}, 'work_')
const overtimeList = useListState({}, 'overtime_')
const leaveQueue = useAsyncData('leave-approval-queue', async (_app, { signal }) => {
  if (!canLeave.value) return null
  return api.request<PaginatedResponse<LeaveApplication>>('leaves/', { signal, query: { ...leaveList.query.value, status: 'PENDING,CANCELLATION_PENDING' } })
}, { watch: [leaveList.query] })
const workQueue = useAsyncData('work-arrangement-approval-queue', async (_app, { signal }) => {
  if (!canWork.value) return null
  return api.request<PaginatedResponse<WorkArrangement>>('work-arrangements/', { signal, query: { ...workList.query.value, status: 'PENDING' } })
}, { watch: [workList.query] })
const overtimeQueue = useAsyncData('overtime-approval-queue', async (_app, { signal }) => {
  if (!canOvertime.value) return null
  return api.request<OvertimePage>('overtime/', { signal, query: { ...overtimeList.query.value, status: 'PENDING' } })
}, { watch: [overtimeList.query] })
const leaveQueueData = useRetainedData(leaveQueue.data)
const workQueueData = useRetainedData(workQueue.data)
const overtimeQueueData = useRetainedData(overtimeQueue.data)
const totalWaiting = computed(() => (leaveQueueData.value?.total || 0) + (workQueueData.value?.total || 0) + (overtimeQueueData.value?.total || 0))
const activePending = computed(() => activeTab.value === 'leave' ? leaveQueue.pending.value : activeTab.value === 'work' ? workQueue.pending.value : overtimeQueue.pending.value)
const activeError = computed(() => activeTab.value === 'leave' ? leaveQueue.error.value : activeTab.value === 'work' ? workQueue.error.value : overtimeQueue.error.value)

function formatDate(value?: string | null) {
  if (!value) return 'Unknown date'
  const date = new Date(value.includes('T') ? value : `${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' }).format(date)
}
function dateRange(item: LeaveApplication) {
  const start = formatDate(item.from_date)
  return item.from_date === item.to_date ? start : `${start} – ${formatDate(item.to_date)}`
}
function requestError(error: unknown, fallback: string) {
  return (error as { data?: { statusMessage?: string } }).data?.statusMessage || fallback
}

async function approveLeave(item: LeaveApplication) {
  actionKey.value = `leave-${item.id}`
  try {
    const isCancellation = item.status === 'CANCELLATION_PENDING'
    await api.request(`leaves/${item.id}${isCancellation ? '/cancellation/approve' : '/approve'}`, { method: 'PATCH' })
    toast.add({
      title: isCancellation ? 'Early return approved' : 'Leave approved',
      description: isCancellation
        ? `Only unused leave from ${formatDate(item.cancellation_effective_date)} has been restored.`
        : `${item.employee_name || 'The employee'} has been notified.`,
      color: 'success',
      icon: 'i-lucide-circle-check'
    })
    await leaveQueue.refresh()
  } catch (error) {
    toast.add({ title: 'Approval failed', description: requestError(error, 'Please try again.'), color: 'error' })
  } finally {
    actionKey.value = ''
  }
}

async function approveWork(item: WorkArrangement) {
  actionKey.value = `work-${item.id}`
  try {
    await api.request(`work-arrangements/${item.id}/approve`, { method: 'PATCH' })
    toast.add({ title: 'Work arrangement approved', color: 'success', icon: 'i-lucide-circle-check' })
    await workQueue.refresh()
  } catch (error) {
    toast.add({ title: 'Approval failed', description: requestError(error, 'Please try again.'), color: 'error' })
  } finally {
    actionKey.value = ''
  }
}

async function approveOvertime(item: OvertimeRecord) {
  actionKey.value = `overtime-${item.id}`
  try {
    await api.request(`overtime/${item.id}/approve`, { method: 'PATCH', body: { approved_minutes: item.calculated_minutes } })
    toast.add({ title: 'Overtime approved', description: `${item.calculated_minutes} minutes approved.`, color: 'success', icon: 'i-lucide-circle-check' })
    await overtimeQueue.refresh()
  } catch (error) {
    toast.add({ title: 'Approval failed', description: requestError(error, 'Please try again.'), color: 'error' })
  } finally {
    actionKey.value = ''
  }
}

function startReject(item: LeaveApplication | WorkArrangement | OvertimeRecord, type: ApprovalTab) {
  rejectionReason.value = ''
  if (type === 'leave') leaveReject.value = item as LeaveApplication
  else if (type === 'work') workReject.value = item as WorkArrangement
  else overtimeReject.value = item as OvertimeRecord
}

function closeReject() {
  leaveReject.value = null
  workReject.value = null
  overtimeReject.value = null
  rejectionReason.value = ''
}

async function rejectRequest() {
  if (actionKey.value) return
  if (rejectionReason.value.trim().length < 3) return
  const type: ApprovalTab = leaveReject.value ? 'leave' : workReject.value ? 'work' : 'overtime'
  const item = leaveReject.value || workReject.value || overtimeReject.value
  if (!item) return
  actionKey.value = `${type}-${item.id}`
  try {
    const path = type === 'leave'
      ? `leaves/${item.id}${(item as LeaveApplication).status === 'CANCELLATION_PENDING' ? '/cancellation/reject' : '/reject'}`
      : type === 'work' ? `work-arrangements/${item.id}/reject` : `overtime/${item.id}/reject`
    const body = type === 'overtime'
      ? { remarks: rejectionReason.value.trim() }
      : { rejection_reason: rejectionReason.value.trim() }
    await api.request(path, { method: 'PATCH', body })
    toast.add({ title: type === 'leave' ? 'Leave rejected' : type === 'work' ? 'Work arrangement rejected' : 'Overtime rejected', color: 'neutral', icon: 'i-lucide-circle-x' })
    closeReject()
    await (type === 'leave' ? leaveQueue.refresh() : type === 'work' ? workQueue.refresh() : overtimeQueue.refresh())
  } catch (error) {
    toast.add({ title: 'Rejection failed', description: requestError(error, 'Please try again.'), color: 'error' })
  } finally {
    actionKey.value = ''
  }
}
</script>

<template>
  <div class="people-page">
    <DataFeedback
      :pending="activePending"
      :error="activeError"
      :has-data="Boolean(activeTab === 'leave' ? leaveQueueData : activeTab === 'work' ? workQueueData : overtimeQueueData)"
    />
    <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Approvals
        </h1><p class="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Review team requests with the context needed to make a confident decision.
        </p>
      </div>
      <UBadge
        color="warning"
        variant="soft"
        size="lg"
        :label="`${totalWaiting} waiting`"
      />
    </div>

    <div
      data-page-tabs
      class="mt-7 flex gap-2 overflow-x-auto border-b border-[var(--people-border)]"
    >
      <button
        v-if="canLeave"
        type="button"
        class="flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="activeTab === 'leave' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        :aria-pressed="activeTab === 'leave'"
        @click="activeTab = 'leave'"
      >
        <UIcon name="i-lucide-calendar-days" />Leave<span class="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{{ leaveQueueData?.total || 0 }}</span>
      </button>
      <button
        v-if="canWork"
        type="button"
        class="flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="activeTab === 'work' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        :aria-pressed="activeTab === 'work'"
        @click="activeTab = 'work'"
      >
        <UIcon name="i-lucide-briefcase-business" />Work arrangements<span class="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{{ workQueueData?.total || 0 }}</span>
      </button>
      <button
        v-if="canOvertime"
        type="button"
        class="flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="activeTab === 'overtime' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        :aria-pressed="activeTab === 'overtime'"
        @click="activeTab = 'overtime'"
      >
        <UIcon name="i-lucide-timer" />Overtime<span class="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{{ overtimeQueueData?.total || 0 }}</span>
      </button>
    </div>

    <ListControls
      v-if="activeTab === 'leave'"
      v-model:search="leaveList.search.value"
      v-model:sort-by="leaveList.sortBy.value"
      v-model:sort-order="leaveList.sortOrder.value"
      :active="leaveList.active.value"
      :sorts="[{ label: 'Submitted', value: 'applied_at' }, { label: 'Status', value: 'status' }]"
      label="Filter leave approvals"
      search-placeholder="Search employee name or code"
      @clear="leaveList.clear"
    />
    <ListControls
      v-else-if="activeTab === 'work'"
      v-model:search="workList.search.value"
      v-model:sort-by="workList.sortBy.value"
      v-model:sort-order="workList.sortOrder.value"
      :active="workList.active.value"
      :sorts="[{ label: 'Submitted', value: 'created_at' }, { label: 'Status', value: 'status' }]"
      label="Filter work arrangement approvals"
      search-placeholder="Search employee name or code"
      @clear="workList.clear"
    />
    <ListControls
      v-else-if="activeTab === 'overtime'"
      v-model:search="overtimeList.search.value"
      v-model:sort-by="overtimeList.sortBy.value"
      v-model:sort-order="overtimeList.sortOrder.value"
      :active="overtimeList.active.value"
      :sorts="[{ label: 'Attendance date', value: 'attendance_date' }, { label: 'Status', value: 'status' }]"
      label="Filter overtime approvals"
      search-placeholder="Search employee name or code"
      @clear="overtimeList.clear"
    />

    <UAlert
      v-if="!canLeave && !canWork && !canOvertime"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-shield-alert"
      title="Approval access is not assigned"
      description="Ask an administrator to assign an approval permission and scope."
    />
    <UAlert
      v-else-if="activeError"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-circle-alert"
      title="Updates could not be loaded"
      description="We couldn’t refresh pending requests right now. Please try again in a moment."
      :actions="[{ label: 'Refresh approvals', onClick: () => activeTab === 'leave' ? leaveQueue.refresh() : activeTab === 'work' ? workQueue.refresh() : overtimeQueue.refresh() }]"
    />

    <div
      v-if="activePending && !(activeTab === 'leave' ? leaveQueueData : activeTab === 'work' ? workQueueData : overtimeQueueData)"
      class="mt-6 grid gap-4 xl:grid-cols-2"
    >
      <div
        v-for="index in 4"
        :key="index"
        class="people-card p-6"
      >
        <USkeleton class="h-5 w-40" /><USkeleton class="mt-4 h-24 w-full" /><USkeleton class="mt-5 h-10 w-full" />
      </div>
    </div>

    <div
      v-else-if="activeTab === 'leave' && leaveQueueData?.total"
      class="mt-6 grid gap-4 xl:grid-cols-2"
    >
      <article
        v-for="item in leaveQueueData?.items"
        :key="item.id"
        class="people-card overflow-hidden"
      >
        <div class="flex items-start gap-4 border-b border-[var(--people-border)] p-5 sm:p-6">
          <UAvatar
            :text="(item.employee_name || `E${item.employee_id}`).split(/\s+/).map(part => part[0]).join('').slice(0, 2)"
            size="lg"
          /><div class="min-w-0 flex-1">
            <h3 class="break-words font-semibold">
              {{ item.employee_name || `Employee #${item.employee_id}` }}
            </h3><p class="mt-1 text-sm text-muted">
              {{ item.employee_code || `Employee ID ${item.employee_id}` }}
            </p>
          </div><UBadge
            label="Pending"
            color="warning"
            variant="soft"
          />
        </div>
        <div class="p-5 sm:p-6">
          <div class="grid gap-3 rounded-2xl bg-[var(--people-forest)] p-4 sm:grid-cols-3">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-muted">
                Leave type
              </p><p class="mt-2 text-sm font-semibold">
                {{ item.leave_type_name || `Leave #${item.leave_type_id}` }}
              </p>
            </div><div>
              <p class="text-xs font-semibold uppercase tracking-wide text-muted">
                Dates
              </p><p class="mt-2 text-sm font-semibold">
                {{ dateRange(item) }}
              </p>
            </div><div>
              <p class="text-xs font-semibold uppercase tracking-wide text-muted">
                Duration
              </p><p class="mt-2 text-sm font-semibold">
                {{ item.days_count }} day{{ item.days_count === 1 ? '' : 's' }}
              </p>
            </div>
          </div><div class="mt-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-muted">
              {{ item.status === 'CANCELLATION_PENDING' ? 'Early-return reason' : 'Employee’s reason' }}
            </p><p class="mt-2 text-sm leading-6">
              {{ item.status === 'CANCELLATION_PENDING' ? item.cancellation_reason : (item.reason || 'No reason provided.') }}
            </p>
            <p
              v-if="item.status === 'CANCELLATION_PENDING'"
              class="mt-2 text-sm text-muted"
            >
              Requested early return from {{ formatDate(item.cancellation_effective_date) }}. Leave already taken remains recorded.
            </p>
          </div><div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <UButton
              v-if="canRejectLeave"
              color="neutral"
              variant="soft"
              icon="i-lucide-x"
              @click="startReject(item, 'leave')"
            >
              Reject
            </UButton><UButton
              icon="i-lucide-check"
              :loading="actionKey === `leave-${item.id}`"
              :disabled="actionKey === `leave-${item.id}`"
              @click="approveLeave(item)"
            >
              {{ item.status === 'CANCELLATION_PENDING' ? 'Approve early return' : 'Approve leave' }}
            </UButton>
          </div>
        </div>
      </article>
    </div>

    <div
      v-else-if="activeTab === 'work' && workQueueData?.total"
      class="mt-6 grid gap-4 xl:grid-cols-2"
    >
      <article
        v-for="item in workQueueData?.items"
        :key="item.id"
        class="people-card overflow-hidden"
      >
        <div class="flex items-start gap-4 border-b border-[var(--people-border)] p-5 sm:p-6">
          <span class="grid size-11 shrink-0 place-items-center rounded-2xl bg-[var(--people-blue)]"><UIcon
            name="i-lucide-briefcase-business"
            class="size-5"
          /></span>
          <div class="min-w-0 flex-1">
            <h3 class="font-semibold">
              Employee #{{ item.employee_id }}
            </h3><p class="mt-1 text-sm capitalize text-muted">
              {{ item.arrangement_type.replaceAll('_', ' ').toLowerCase() }}
            </p>
          </div>
          <UBadge
            label="Pending"
            color="warning"
            variant="soft"
          />
        </div>
        <div class="p-5 sm:p-6">
          <div class="grid gap-3 rounded-2xl bg-muted/5 p-4 sm:grid-cols-2">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-muted">
                Dates
              </p><p class="mt-2 text-sm font-semibold">
                {{ formatDate(item.from_date) }}<span v-if="item.to_date !== item.from_date"> – {{ formatDate(item.to_date) }}</span>
              </p>
            </div><div v-if="item.destination_location">
              <p class="text-xs font-semibold uppercase tracking-wide text-muted">
                Destination
              </p><p class="mt-2 text-sm font-semibold">
                {{ item.destination_location }}
              </p>
            </div>
          </div>
          <div class="mt-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-muted">
              Employee’s reason
            </p><p class="mt-2 text-sm leading-6">
              {{ item.reason }}
            </p>
          </div>
          <div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <UButton
              color="neutral"
              variant="soft"
              icon="i-lucide-x"
              @click="startReject(item, 'work')"
            >
              Reject
            </UButton><UButton
              icon="i-lucide-check"
              :loading="actionKey === `work-${item.id}`"
              :disabled="actionKey === `work-${item.id}`"
              @click="approveWork(item)"
            >
              Approve arrangement
            </UButton>
          </div>
        </div>
      </article>
    </div>

    <section
      v-else-if="activeTab === 'overtime' && overtimeQueueData?.items.length"
      class="mt-6 grid gap-4 xl:grid-cols-2"
    >
      <article
        v-for="item in overtimeQueueData.items"
        :key="item.id"
        class="people-card overflow-hidden"
      >
        <div class="flex items-start gap-4 border-b border-[var(--people-border)] p-5 sm:p-6">
          <span class="grid size-11 shrink-0 place-items-center rounded-2xl bg-[var(--people-yellow)]"><UIcon
            name="i-lucide-timer"
            class="size-5"
          /></span>
          <div class="min-w-0 flex-1">
            <h3 class="font-semibold">
              {{ item.employee_name || `Employee #${item.employee_id}` }}
            </h3>
            <p class="mt-1 text-sm text-muted">
              {{ item.employee_code }} · {{ item.attendance_date }}
            </p>
          </div>
          <UBadge
            label="Pending"
            color="warning"
            variant="soft"
          />
        </div>
        <div class="p-5 sm:p-6">
          <div class="grid gap-3 rounded-2xl bg-muted/5 p-4 sm:grid-cols-2">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-muted">
                Calculated overtime
              </p>
              <p class="mt-2 text-sm font-semibold">
                {{ item.calculated_minutes }} minutes
              </p>
            </div>
            <div v-if="item.overtime_start || item.overtime_end">
              <p class="text-xs font-semibold uppercase tracking-wide text-muted">
                Time window
              </p>
              <p class="mt-2 text-sm font-semibold">
                {{ item.overtime_start || '—' }} – {{ item.overtime_end || '—' }}
              </p>
            </div>
          </div>
          <div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <UButton
              color="neutral"
              variant="soft"
              icon="i-lucide-x"
              @click="startReject(item, 'overtime')"
            >
              Reject
            </UButton>
            <UButton
              icon="i-lucide-check"
              :loading="actionKey === `overtime-${item.id}`"
              :disabled="item.calculated_minutes <= 0"
              @click="approveOvertime(item)"
            >
              {{ item.calculated_minutes > 0 ? `Approve ${item.calculated_minutes} minutes` : 'No minutes to approve' }}
            </UButton>
          </div>
        </div>
      </article>
    </section>

    <div
      v-else-if="!activeError && (canLeave || canWork || canOvertime)"
      class="people-card mt-6 flex flex-col items-center px-6 py-16 text-center"
    >
      <span class="grid size-14 place-items-center rounded-2xl bg-[var(--people-mint)]"><UIcon
        name="i-lucide-circle-check-big"
        class="size-7"
      /></span><h3 class="mt-5 text-lg font-semibold">
        Everything is reviewed
      </h3><p class="mt-2 max-w-sm text-sm leading-6 text-muted">
        There are no {{ activeTab }} requests waiting for your action.
      </p>
    </div>

    <UModal
      :open="!!(leaveReject || workReject || overtimeReject)"
      title="Reject request"
      description="Give a clear reason for rejecting this request."
      @update:open="value => { if (!value) closeReject() }"
    >
      <template #body>
        <section class="w-full space-y-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-sm font-semibold text-rose-600">
                Reject {{ leaveReject ? 'leave request' : workReject ? 'work arrangement' : 'overtime request' }}
              </p><h3 class="mt-1 text-xl font-semibold">
                Add a clear reason
              </h3>
            </div><UButton
              icon="i-lucide-x"
              color="neutral"
              variant="ghost"
              aria-label="Close"
              @click="closeReject"
            />
          </div><p class="mt-4 text-sm leading-6 text-muted">
            The employee will see this explanation with the rejected request.
          </p><UFormField
            class="mt-5"
            label="Rejection reason"
            :error="rejectionReason && rejectionReason.trim().length < 3 ? 'Enter at least 3 characters.' : undefined"
            required
          >
            <UTextarea
              v-model="rejectionReason"
              class="w-full"
              :rows="4"
              placeholder="Explain why this request cannot be approved."
              autofocus
            />
          </UFormField><div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <UButton
              color="neutral"
              variant="soft"
              @click="closeReject"
            >
              Cancel
            </UButton><UButton
              color="error"
              icon="i-lucide-circle-x"
              :loading="Boolean(actionKey)"
              :disabled="Boolean(actionKey) || rejectionReason.trim().length < 3"
              @click="rejectRequest"
            >
              Reject request
            </UButton>
          </div>
        </section>
      </template>
    </UModal>
    <ListPagination
      v-if="activeTab === 'leave' && leaveQueueData"
      v-model:page="leaveList.page.value"
      v-model:page-size="leaveList.pageSize.value"
      :total="leaveQueueData?.total || 0"
      :total-pages="leaveQueueData?.total_pages"
      :loading="leaveQueue.pending.value"
    />
    <ListPagination
      v-if="activeTab === 'work' && workQueueData"
      v-model:page="workList.page.value"
      v-model:page-size="workList.pageSize.value"
      :total="workQueueData?.total || 0"
      :total-pages="workQueueData?.total_pages"
      :loading="workQueue.pending.value"
    />
    <ListPagination
      v-if="activeTab === 'overtime' && overtimeQueueData"
      v-model:page="overtimeList.page.value"
      v-model:page-size="overtimeList.pageSize.value"
      :total="overtimeQueueData?.total || 0"
      :total-pages="overtimeQueueData?.total_pages"
      :loading="overtimeQueue.pending.value"
    />
  </div>
</template>
