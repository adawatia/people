<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
import type { AttendanceCorrection, AttendanceRecord } from '#shared/types/attendance'
import type { LeaveApplication } from '#shared/types/leave'
import type { WorkArrangement } from '#shared/types/work-arrangement'

interface CorrectionReview extends AttendanceCorrection { record?: AttendanceRecord }
type ApprovalTab = 'attendance' | 'leave' | 'work'

useSeoMeta({ title: 'Approvals' })
const api = useHrmsApi()
const auth = useAuth()
const toast = useToast()
const canAttendance = computed(() => auth.hasPermission('attendance.approve_correction'))
const canLeave = computed(() => auth.hasPermission('leave.approve'))
const canRejectLeave = computed(() => auth.hasPermission('leave.reject'))
const canWork = computed(() => auth.hasPermission('work_arrangement.approve'))
const activeTab = ref<ApprovalTab>(canAttendance.value ? 'attendance' : 'leave')
const actionKey = ref('')
const attendanceReject = ref<CorrectionReview | null>(null)
const leaveReject = ref<LeaveApplication | null>(null)
const workReject = ref<WorkArrangement | null>(null)
const rejectionReason = ref('')

const attendanceQueue = useAsyncData('attendance-approval-queue', async () => {
  if (!canAttendance.value) return []
  const items = await api.request<AttendanceCorrection[]>('attendance/corrections', { query: { status: 'PENDING' } })
  return await Promise.all(items.map(async (item) => {
    try {
      return { ...item, record: await api.request<AttendanceRecord>(`attendance/records/${item.attendance_record_id}`) }
    } catch { return item }
  })) as CorrectionReview[]
})

const leaveQueue = useAsyncData('leave-approval-queue', async () => {
  if (!canLeave.value) return []
  return await api.request<LeaveApplication[]>('leaves/', { query: { status: 'PENDING' } })
})

const workQueue = useAsyncData('work-arrangement-approval-queue', async () => {
  if (!canWork.value) return []
  return await api.request<WorkArrangement[]>('work-arrangements/', { query: { status: 'PENDING' } })
})

const totalWaiting = computed(() => (attendanceQueue.data.value?.length || 0) + (leaveQueue.data.value?.length || 0) + (workQueue.data.value?.length || 0))
const activePending = computed(() => activeTab.value === 'attendance' ? attendanceQueue.pending.value : activeTab.value === 'leave' ? leaveQueue.pending.value : workQueue.pending.value)
const activeError = computed(() => activeTab.value === 'attendance' ? attendanceQueue.error.value : activeTab.value === 'leave' ? leaveQueue.error.value : workQueue.error.value)

function formatTime(value?: string | null) {
  if (!value) return '—'
  const [hours, minutes] = value.split(':')
  return new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit' }).format(new Date(2000, 0, 1, Number(hours), Number(minutes)))
}
function formatDate(value?: string) {
  if (!value) return 'Unknown date'
  return new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(`${value}T00:00:00`))
}
function dateRange(item: LeaveApplication) {
  const start = formatDate(item.from_date)
  return item.from_date === item.to_date ? start : `${start} – ${formatDate(item.to_date)}`
}
function requestError(error: unknown, fallback: string) {
  return (error as { data?: { statusMessage?: string } }).data?.statusMessage || fallback
}

async function approveAttendance(item: CorrectionReview) {
  actionKey.value = `attendance-${item.id}`
  try {
    await api.request(`attendance/corrections/${item.id}/approve`, { method: 'PATCH' })
    toast.add({ title: 'Correction approved', description: 'The attendance record has been updated.', color: 'success', icon: 'i-lucide-circle-check' })
    await attendanceQueue.refresh()
  } catch (error) {
    toast.add({ title: 'Approval failed', description: requestError(error, 'Please try again.'), color: 'error' })
  } finally {
    actionKey.value = ''
  }
}

async function approveLeave(item: LeaveApplication) {
  actionKey.value = `leave-${item.id}`
  try {
    await api.request(`leaves/${item.id}/approve`, { method: 'PATCH' })
    toast.add({ title: 'Leave approved', description: `${item.employee_name || 'The employee'} has been notified.`, color: 'success', icon: 'i-lucide-circle-check' })
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
  } finally { actionKey.value = '' }
}

function startReject(item: CorrectionReview | LeaveApplication | WorkArrangement, type: ApprovalTab) {
  rejectionReason.value = ''
  if (type === 'attendance') attendanceReject.value = item as CorrectionReview
  else if (type === 'leave') leaveReject.value = item as LeaveApplication
  else workReject.value = item as WorkArrangement
}

function closeReject() {
  attendanceReject.value = null
  leaveReject.value = null
  workReject.value = null
  rejectionReason.value = ''
}

async function rejectRequest() {
  if (rejectionReason.value.trim().length < 3) return
  const type: ApprovalTab = attendanceReject.value ? 'attendance' : leaveReject.value ? 'leave' : 'work'
  const item = attendanceReject.value || leaveReject.value || workReject.value
  if (!item) return
  actionKey.value = `${type}-${item.id}`
  try {
    const path = type === 'attendance' ? `attendance/corrections/${item.id}/reject` : type === 'leave' ? `leaves/${item.id}/reject` : `work-arrangements/${item.id}/reject`
    await api.request(path, { method: 'PATCH', body: { rejection_reason: rejectionReason.value.trim() } })
    toast.add({ title: type === 'attendance' ? 'Correction rejected' : 'Leave rejected', color: 'neutral', icon: 'i-lucide-circle-x' })
    closeReject()
    await (type === 'attendance' ? attendanceQueue.refresh() : type === 'leave' ? leaveQueue.refresh() : workQueue.refresh())
  } catch (error) {
    toast.add({ title: 'Rejection failed', description: requestError(error, 'Please try again.'), color: 'error' })
  } finally {
    actionKey.value = ''
  }
}
</script>

<template>
  <div>
    <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p class="text-sm font-medium text-primary">
          Manager workspace
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Approvals
        </h2><p class="mt-2 max-w-2xl text-sm leading-6 text-muted">
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

    <div class="mt-7 flex gap-2 overflow-x-auto border-b border-[var(--people-border)]">
      <button
        v-if="canAttendance"
        type="button"
        class="flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="activeTab === 'attendance' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        @click="activeTab = 'attendance'"
      >
        <UIcon name="i-lucide-clock-alert" />Attendance<span class="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{{ attendanceQueue.data.value?.length || 0 }}</span>
      </button>
      <button
        v-if="canLeave"
        type="button"
        class="flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="activeTab === 'leave' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        @click="activeTab = 'leave'"
      >
        <UIcon name="i-lucide-calendar-days" />Leave<span class="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{{ leaveQueue.data.value?.length || 0 }}</span>
      </button>
      <button
        v-if="canWork"
        type="button"
        class="flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="activeTab === 'work' ? 'border-primary text-primary' : 'border-transparent text-muted'"
        @click="activeTab = 'work'"
      >
        <UIcon name="i-lucide-briefcase-business" />Work arrangements<span class="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{{ workQueue.data.value?.length || 0 }}</span>
      </button>
    </div>

    <UAlert
      v-if="!canAttendance && !canLeave && !canWork"
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
      icon="i-lucide-coffee"
      title="Your approval queue is taking a short break"
      description="We couldn’t refresh pending requests right now. Please try again in a moment."
      :actions="[{ label: 'Refresh approvals', onClick: () => activeTab === 'attendance' ? attendanceQueue.refresh() : activeTab === 'leave' ? leaveQueue.refresh() : workQueue.refresh() }]"
    />

    <div
      v-if="activePending"
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
      v-else-if="activeTab === 'attendance' && attendanceQueue.data.value?.length"
      class="mt-6 grid gap-4 xl:grid-cols-2"
    >
      <article
        v-for="item in attendanceQueue.data.value"
        :key="item.id"
        class="people-card overflow-hidden"
      >
        <div class="flex items-start gap-4 border-b border-[var(--people-border)] p-5 sm:p-6">
          <span class="grid size-11 shrink-0 place-items-center rounded-2xl bg-[var(--people-peach)]"><UIcon
            name="i-lucide-clock-alert"
            class="size-5"
          /></span><div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="font-semibold">
                Employee #{{ item.record?.employee_id || '—' }}
              </h3><AttendanceStatusBadge
                v-if="item.record"
                :status="item.record.status"
              />
            </div><p class="mt-1 text-sm text-muted">
              {{ formatDate(item.record?.attendance_date) }}
            </p>
          </div><UBadge
            label="Pending"
            color="warning"
            variant="soft"
          />
        </div>
        <div class="p-5 sm:p-6">
          <div class="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-2xl bg-muted/5 p-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-muted">
                Recorded
              </p><p class="mt-2 text-sm font-semibold tabular-nums">
                {{ formatTime(item.record?.punch_in) }} – {{ formatTime(item.record?.punch_out) }}
              </p>
            </div><UIcon
              name="i-lucide-arrow-right"
              class="size-5 text-muted"
            /><div>
              <p class="text-xs font-semibold uppercase tracking-wide text-primary">
                Requested
              </p><p class="mt-2 text-sm font-semibold tabular-nums">
                {{ formatTime(item.requested_punch_in || item.record?.punch_in) }} – {{ formatTime(item.requested_punch_out || item.record?.punch_out) }}
              </p>
            </div>
          </div><p class="mt-4 text-sm leading-6">
            <span class="mr-2 text-xs font-semibold uppercase tracking-wide text-muted">Reason</span>{{ item.reason }}
          </p><div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <UButton
              color="neutral"
              variant="soft"
              icon="i-lucide-x"
              @click="startReject(item, 'attendance')"
            >
              Reject
            </UButton><UButton
              icon="i-lucide-check"
              :loading="actionKey === `attendance-${item.id}`"
              @click="approveAttendance(item)"
            >
              Approve correction
            </UButton>
          </div>
        </div>
      </article>
    </div>

    <div
      v-else-if="activeTab === 'leave' && leaveQueue.data.value?.length"
      class="mt-6 grid gap-4 xl:grid-cols-2"
    >
      <article
        v-for="item in leaveQueue.data.value"
        :key="item.id"
        class="people-card overflow-hidden"
      >
        <div class="flex items-start gap-4 border-b border-[var(--people-border)] p-5 sm:p-6">
          <UAvatar
            :text="(item.employee_name || `E${item.employee_id}`).split(/\s+/).map(part => part[0]).join('').slice(0, 2)"
            size="lg"
          /><div class="min-w-0 flex-1">
            <h3 class="truncate font-semibold">
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
          <div class="grid gap-3 rounded-2xl bg-[var(--people-lavender)] p-4 sm:grid-cols-3">
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
              Employee’s reason
            </p><p class="mt-2 text-sm leading-6">
              {{ item.reason || 'No reason provided.' }}
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
              @click="approveLeave(item)"
            >
              Approve leave
            </UButton>
          </div>
        </div>
      </article>
    </div>

    <div
      v-else-if="activeTab === 'work' && workQueue.data.value?.length"
      class="mt-6 grid gap-4 xl:grid-cols-2"
    >
      <article
        v-for="item in workQueue.data.value"
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
              @click="approveWork(item)"
            >
              Approve arrangement
            </UButton>
          </div>
        </div>
      </article>
    </div>

    <div
      v-else-if="!activeError && (canAttendance || canLeave || canWork)"
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

    <div
      v-if="attendanceReject || leaveReject || workReject"
      class="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/40 backdrop-blur-[2px] sm:items-center sm:p-6"
      @click.self="closeReject"
    >
      <section class="w-full max-w-lg rounded-t-3xl bg-[var(--people-surface)] p-6 shadow-2xl sm:rounded-2xl sm:p-7">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-semibold text-rose-600">
              Reject {{ attendanceReject ? 'correction' : leaveReject ? 'leave request' : 'work arrangement' }}
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
            :disabled="rejectionReason.trim().length < 3"
            @click="rejectRequest"
          >
            Reject request
          </UButton>
        </div>
      </section>
    </div>
  </div>
</template>
