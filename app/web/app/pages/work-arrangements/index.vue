<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
import type { WorkArrangement, WorkArrangementType } from '#shared/types/work-arrangement'

useSeoMeta({ title: 'Work arrangements' })
const auth = useAuth()
const api = useHrmsApi()
const toast = useToast()
const employeeId = computed(() => auth.user.value?.employee_id)
const requestOpen = ref(false)
const submitting = ref(false)
const cancellingId = ref<number | null>(null)
const filter = ref('ALL')
const today = new Date().toISOString().slice(0, 10)
const form = reactive({ arrangement_type: 'WORK_FROM_HOME' as WorkArrangementType, from_date: today, to_date: today, reason: '', destination_location: '', contact_phone: '' })

const typeConfig: Record<WorkArrangementType, { label: string, description: string, icon: string, tone: string }> = {
  WORK_FROM_HOME: { label: 'Work from home', description: 'Request to work remotely from your residence', icon: 'i-lucide-house-wifi', tone: 'var(--people-lavender)' },
  OUT_DUTY: { label: 'Out duty', description: 'Official work away from your workplace', icon: 'i-lucide-building-2', tone: 'var(--people-blue)' },
  FIELD_WORK: { label: 'Field work', description: 'Work at a client or field location', icon: 'i-lucide-map-pin', tone: 'var(--people-peach)' },
  OFFICE: { label: 'Office', description: 'Temporary office-based arrangement', icon: 'i-lucide-briefcase-business', tone: 'var(--people-mint)' }
}

const { data: requests, pending, error, refresh } = await useAsyncData('my-work-arrangements', async () => {
  if (!employeeId.value) return []
  return await api.request<WorkArrangement[]>('work-arrangements/', { query: { employee_id: employeeId.value } })
}, { watch: [employeeId] })
const filtered = computed(() => (requests.value || []).filter(item => filter.value === 'ALL' || item.status === filter.value))
const requestDays = computed(() => {
  const from = new Date(`${form.from_date}T00:00:00`)
  const to = new Date(`${form.to_date}T00:00:00`)
  return to >= from ? Math.floor((to.getTime() - from.getTime()) / 86400000) + 1 : 0
})
const formValid = computed(() => requestDays.value > 0 && form.reason.trim().length >= 5)

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${value}T00:00:00`))
}
function statusColor(status: string): 'warning' | 'success' | 'error' | 'neutral' {
  return status === 'PENDING' ? 'warning' : status === 'APPROVED' ? 'success' : status === 'REJECTED' ? 'error' : 'neutral'
}
function openRequest() {
  Object.assign(form, { arrangement_type: 'WORK_FROM_HOME', from_date: today, to_date: today, reason: '', destination_location: '', contact_phone: '' })
  requestOpen.value = true
}
async function submitRequest() {
  if (!employeeId.value || !formValid.value) return
  submitting.value = true
  try {
    await api.request<WorkArrangement>('work-arrangements/', {
      method: 'POST',
      body: {
        employee_id: employeeId.value,
        arrangement_type: form.arrangement_type,
        from_date: form.from_date,
        to_date: form.to_date,
        reason: form.reason.trim(),
        destination_location: form.destination_location.trim() || null,
        contact_phone: form.contact_phone.trim() || null
      }
    })
    requestOpen.value = false
    toast.add({ title: 'Work arrangement requested', description: 'Your request is ready for review.', color: 'success', icon: 'i-lucide-circle-check' })
    await refresh()
  } catch (submitError) {
    const message = (submitError as { data?: { statusMessage?: string } }).data?.statusMessage
    toast.add({ title: 'Could not submit request', description: message || 'Check the dates and try again.', color: 'error' })
  } finally { submitting.value = false }
}
async function cancelRequest(item: WorkArrangement) {
  if (!confirm(`Cancel this ${typeConfig[item.arrangement_type].label.toLowerCase()} request?`)) return
  cancellingId.value = item.id
  try {
    await api.request(`work-arrangements/${item.id}/cancel`, { method: 'PATCH' })
    toast.add({ title: 'Request cancelled', color: 'neutral', icon: 'i-lucide-ban' })
    await refresh()
  } catch (cancelError) {
    const message = (cancelError as { data?: { statusMessage?: string } }).data?.statusMessage
    toast.add({ title: 'Could not cancel request', description: message || 'Please try again.', color: 'error' })
  } finally { cancellingId.value = null }
}
</script>

<template>
  <div>
    <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p class="text-sm font-medium text-primary">
          Flexible work
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Work arrangements
        </h2><p class="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Request to work from home and follow the status of your requests.
        </p>
      </div><UButton
        size="lg"
        icon="i-lucide-plus"
        :disabled="!employeeId"
        @click="openRequest"
      >
        New request
      </UButton>
    </div>
    <UAlert
      v-if="!employeeId"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-user-round-x"
      title="No employee profile is linked"
      description="Ask your administrator to link this account before creating requests."
    />
    <UAlert
      v-else-if="error"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-coffee"
      title="Your work plans are taking a short break"
      description="We couldn’t refresh your work arrangement requests right now. Please try again in a moment."
      :actions="[{ label: 'Refresh requests', onClick: () => refresh() }]"
    />
    <UAlert
      v-else
      class="mt-6"
      color="info"
      variant="soft"
      icon="i-lucide-construction"
      title="Work from home requests are in progress"
      description="This feature is being built step by step. For now, you can submit and track work-from-home requests here."
    />

    <template v-if="employeeId">
      <div class="mt-7 max-w-xl">
        <article class="people-card p-5">
          <span
            class="grid size-11 place-items-center rounded-2xl"
            :style="{ background: typeConfig.WORK_FROM_HOME.tone }"
          ><UIcon
            :name="typeConfig.WORK_FROM_HOME.icon"
            class="size-5"
          /></span><h3 class="mt-4 font-semibold">
            {{ typeConfig.WORK_FROM_HOME.label }}
          </h3><p class="mt-2 text-sm leading-6 text-muted">
            {{ typeConfig.WORK_FROM_HOME.description }}
          </p>
        </article>
      </div>
      <section class="people-card mt-7 overflow-hidden">
        <div class="flex flex-col gap-4 border-b border-[var(--people-border)] p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <h3 class="font-semibold">
              Request history
            </h3><p class="mt-1 text-sm text-muted">
              Current and previous work arrangements
            </p>
          </div><div class="flex gap-1 overflow-x-auto rounded-xl bg-muted/5 p-1">
            <button
              v-for="option in ['ALL', 'PENDING', 'APPROVED', 'REJECTED']"
              :key="option"
              type="button"
              class="rounded-lg px-3 py-2 text-xs font-semibold"
              :class="filter === option ? 'bg-[var(--people-surface)] shadow-sm' : 'text-muted'"
              @click="filter = option"
            >
              {{ option === 'ALL' ? 'All' : option.charAt(0) + option.slice(1).toLowerCase() }}
            </button>
          </div>
        </div>
        <div
          v-if="pending"
          class="grid gap-4 p-5 sm:grid-cols-2"
        >
          <USkeleton
            v-for="index in 4"
            :key="index"
            class="h-40 rounded-2xl"
          />
        </div>
        <div
          v-else-if="filtered.length"
          class="grid gap-0 divide-y divide-[var(--people-border)] lg:grid-cols-2 lg:divide-x lg:divide-y-0"
        >
          <article
            v-for="item in filtered"
            :key="item.id"
            class="p-5 sm:p-6"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex min-w-0 items-center gap-3">
                <span
                  class="grid size-10 shrink-0 place-items-center rounded-xl"
                  :style="{ background: typeConfig[item.arrangement_type].tone }"
                ><UIcon
                  :name="typeConfig[item.arrangement_type].icon"
                  class="size-5"
                /></span><div class="min-w-0">
                  <h4 class="truncate font-semibold">
                    {{ typeConfig[item.arrangement_type].label }}
                  </h4><p class="mt-1 text-xs text-muted">
                    {{ formatDate(item.from_date) }}<span v-if="item.to_date !== item.from_date"> – {{ formatDate(item.to_date) }}</span> · {{ Math.floor((new Date(`${item.to_date}T00:00:00`).getTime() - new Date(`${item.from_date}T00:00:00`).getTime()) / 86400000) + 1 }} day(s)
                  </p>
                </div>
              </div><UBadge
                :label="item.status.charAt(0) + item.status.slice(1).toLowerCase()"
                :color="statusColor(item.status)"
                variant="soft"
              />
            </div><p class="mt-4 text-sm leading-6 text-muted">
              {{ item.reason }}
            </p><div
              v-if="item.destination_location"
              class="mt-3 flex items-center gap-2 text-xs text-muted"
            >
              <UIcon name="i-lucide-map-pin" />{{ item.destination_location }}
            </div><p
              v-if="item.rejection_reason"
              class="mt-3 rounded-xl bg-rose-50 p-3 text-xs leading-5 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200"
            >
              {{ item.rejection_reason }}
            </p><UButton
              v-if="['PENDING', 'APPROVED'].includes(item.status)"
              class="mt-4"
              size="sm"
              color="neutral"
              variant="soft"
              :loading="cancellingId === item.id"
              @click="cancelRequest(item)"
            >
              Cancel request
            </UButton>
          </article>
        </div>
        <div
          v-else
          class="px-6 py-14 text-center"
        >
          <UIcon
            name="i-lucide-briefcase-business"
            class="mx-auto size-8 text-muted"
          /><p class="mt-3 text-sm font-semibold">
            No work arrangement requests yet
          </p><p class="mt-1 text-xs text-muted">
            Your requests will appear here when you need to work from home.
          </p>
        </div>
      </section>
    </template>

    <div
      v-if="requestOpen"
      class="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/40 backdrop-blur-[2px] sm:items-center sm:p-6"
      @click.self="requestOpen = false"
    >
      <section class="max-h-[94dvh] w-full overflow-y-auto rounded-t-3xl bg-[var(--people-surface)] p-5 shadow-2xl sm:max-w-2xl sm:rounded-2xl sm:p-7">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm font-semibold text-primary">
              New request
            </p><h3 class="mt-1 text-2xl font-semibold">
              Request work from home
            </h3>
          </div><UButton
            icon="i-lucide-x"
            color="neutral"
            variant="ghost"
            aria-label="Close"
            @click="requestOpen = false"
          />
        </div><div class="mt-6 grid gap-5 sm:grid-cols-2">
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
          </UFormField><UFormField
            label="To"
            required
          >
            <UInput
              v-model="form.to_date"
              class="w-full"
              type="date"
              size="xl"
              :min="form.from_date"
            />
          </UFormField><UFormField
            class="sm:col-span-2"
            label="Contact phone"
            help="Optional number where you can be reached during this arrangement."
          >
            <UInput
              v-model="form.contact_phone"
              class="w-full"
              size="xl"
              type="tel"
              icon="i-lucide-phone"
            />
          </UFormField><UFormField
            class="sm:col-span-2"
            label="Reason"
            required
          >
            <UTextarea
              v-model="form.reason"
              class="w-full"
              :rows="4"
              placeholder="Explain the business or personal context for your approver."
            />
          </UFormField>
        </div><div class="mt-5 rounded-2xl bg-[var(--people-lavender)] p-4 text-sm">
          <span class="font-semibold">{{ requestDays }} day{{ requestDays === 1 ? '' : 's' }}</span><span class="ml-2 text-muted">requested as {{ typeConfig[form.arrangement_type].label.toLowerCase() }}</span>
        </div><div class="sticky bottom-0 -mx-5 mt-6 flex flex-col-reverse gap-3 border-t border-[var(--people-border)] bg-[var(--people-surface)] px-5 pt-4 sm:static sm:mx-0 sm:flex-row sm:justify-end sm:border-0 sm:p-0">
          <UButton
            color="neutral"
            variant="soft"
            @click="requestOpen = false"
          >
            Cancel
          </UButton><UButton
            icon="i-lucide-send"
            :loading="submitting"
            :disabled="!formValid"
            @click="submitRequest"
          >
            Submit request
          </UButton>
        </div>
      </section>
    </div>
  </div>
</template>
