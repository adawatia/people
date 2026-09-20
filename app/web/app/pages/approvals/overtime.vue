<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
import type { OvertimeRecord } from '#shared/types/overtime'

useSeoMeta({ title: 'Overtime approvals' })
const api = useHrmsApi()
const toast = useToast()
const actionId = ref<number | null>(null)
const review = ref<OvertimeRecord | null>(null)
const reviewOpen = computed({
  get: () => review.value !== null,
  set: (value) => { if (!value) review.value = null }
})
const approvedMinutes = ref(0)
const remarks = ref('')
const { data, pending, error, refresh } = await useAsyncData('overtime-approvals', () => api.request<OvertimeRecord[]>('overtime/', { query: { status: 'PENDING' } }))
const hours = (minutes: number) => `${Math.floor(minutes / 60)}h ${minutes % 60}m`
function startReview(item: OvertimeRecord) {
  review.value = item
  approvedMinutes.value = item.calculated_minutes
  remarks.value = ''
}
async function approve() {
  if (!review.value || approvedMinutes.value < 0 || approvedMinutes.value > review.value.calculated_minutes) return
  actionId.value = review.value.id
  try {
    await api.request(`overtime/${review.value.id}/approve`, { method: 'PATCH', body: { approved_minutes: approvedMinutes.value, remarks: remarks.value || null } })
    toast.add({ title: 'Overtime approved', color: 'success', icon: 'i-lucide-circle-check' })
    review.value = null
    await refresh()
  } finally { actionId.value = null }
}
async function reject(item: OvertimeRecord) {
  const reason = prompt('Reason for rejecting this overtime record?')
  if (reason === null) return
  actionId.value = item.id
  try {
    await api.request(`overtime/${item.id}/reject`, { method: 'PATCH', body: { remarks: reason || null } })
    toast.add({ title: 'Overtime rejected', color: 'neutral', icon: 'i-lucide-circle-x' })
    await refresh()
  } finally { actionId.value = null }
}
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Manager workspace
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Overtime approvals
        </h2><p class="mt-2 text-sm text-muted">
          Review calculated overtime and confirm payable minutes.
        </p>
      </div>
      <UButton
        to="/approvals"
        color="neutral"
        variant="soft"
        icon="i-lucide-arrow-left"
      >
        All approvals
      </UButton>
    </div>
    <UAlert
      v-if="error"
      class="mt-6"
      color="error"
      variant="soft"
      title="Overtime requests are unavailable"
      :actions="[{ label: 'Try again', onClick: () => refresh() }]"
    />
    <section class="mt-7 grid gap-4 lg:grid-cols-2">
      <template v-if="pending">
        <div
          v-for="i in 4"
          :key="i"
          class="people-card p-5"
        >
          <USkeleton class="h-24 w-full" />
        </div>
      </template>
      <article
        v-for="item in data"
        v-else
        :key="item.id"
        class="people-card p-5 sm:p-6"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="font-semibold">
              Employee #{{ item.employee_id }}
            </p><p class="mt-1 text-xs text-muted">
              Attendance record #{{ item.attendance_record_id }}
            </p>
          </div><UBadge
            color="warning"
            variant="soft"
          >
            Pending
          </UBadge>
        </div>
        <div class="mt-5 rounded-xl bg-muted/5 p-4">
          <p class="text-xs font-medium uppercase tracking-wide text-muted">
            Calculated overtime
          </p><p class="mt-2 text-2xl font-semibold tabular-nums">
            {{ hours(item.calculated_minutes) }}
          </p>
        </div>
        <div class="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <UButton
            color="error"
            variant="soft"
            icon="i-lucide-x"
            :loading="actionId === item.id"
            @click="reject(item)"
          >
            Reject
          </UButton><UButton
            icon="i-lucide-check"
            @click="startReview(item)"
          >
            Review & approve
          </UButton>
        </div>
      </article>
    </section>
    <div
      v-if="!pending && !error && !data?.length"
      class="people-card mt-7 p-12 text-center"
    >
      <UIcon
        name="i-lucide-badge-check"
        class="mx-auto size-10 text-muted"
      /><h3 class="mt-4 font-semibold">
        No overtime waiting
      </h3><p class="mt-1 text-sm text-muted">
        All overtime records have been reviewed.
      </p>
    </div>
    <UModal
      v-model:open="reviewOpen"
      title="Approve overtime"
    >
      <template #body>
        <div class="space-y-5">
          <UFormField
            label="Approved minutes"
            help="Cannot exceed the calculated amount"
          >
            <UInput
              v-model.number="approvedMinutes"
              class="w-full"
              type="number"
              :min="0"
              :max="review?.calculated_minutes"
            />
          </UFormField><UFormField label="Remarks">
            <UTextarea
              v-model="remarks"
              class="w-full"
              :rows="3"
            />
          </UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            color="neutral"
            variant="ghost"
            @click="review = null"
          >
            Cancel
          </UButton><UButton
            :loading="actionId === review?.id"
            @click="approve"
          >
            Approve {{ hours(approvedMinutes) }}
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
