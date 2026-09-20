<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes, @stylistic/max-statements-per-line */
import type { EmployeePage } from '#shared/types/employee'
import type { Unit } from '#shared/types/organization'
import type { Shift, ShiftAssignment } from '#shared/types/workforce'

useSeoMeta({ title: 'Shifts' })
const api = useHrmsApi(); const auth = useAuth(); const toast = useToast()
const tab = ref<'definitions' | 'assignments'>('definitions'); const createOpen = ref(false); const assignOpen = ref(false); const saving = ref(false)
const today = new Date().toISOString().slice(0, 10)
const shiftForm = reactive({ name: '', code: '', unit_id: undefined as number | undefined, start_time: '09:00', end_time: '18:00', grace_minutes: 10, break_minutes: 30, enable_auto_attendance: true })
const assignmentForm = reactive({ employee_id: undefined as number | undefined, shift_id: undefined as number | undefined, effective_from: today, effective_to: '' })
const canManage = computed(() => auth.hasPermission('shift.assign'))
const { data, pending, error, refresh } = await useAsyncData('shift-workspace', async () => {
  const [shifts, assignments, units, employees] = await Promise.all([api.request<Shift[]>('shifts/', { query: { is_active: true } }), api.request<ShiftAssignment[]>('shifts/assignments'), api.request<Unit[]>('org/units'), api.request<EmployeePage>('employees/', { query: { page_size: 100, status: 'ACTIVE' } })])
  return { shifts, assignments, units, employees: employees.items }
})
const time = (value: string) => value?.slice(0, 5) || '—'
function newShift() { Object.assign(shiftForm, { name: '', code: '', unit_id: undefined, start_time: '09:00', end_time: '18:00', grace_minutes: 10, break_minutes: 30, enable_auto_attendance: true }); createOpen.value = true }
async function createShift() {
  if (!shiftForm.name.trim()) return
  saving.value = true
  try { await api.request('shifts/', { method: 'POST', body: { ...shiftForm, code: shiftForm.code || null, is_cross_midnight: shiftForm.end_time <= shiftForm.start_time } }); createOpen.value = false; toast.add({ title: 'Shift created', color: 'success' }); await refresh() } finally { saving.value = false }
}
function newAssignment() { assignmentForm.employee_id = data.value?.employees[0]?.id; assignmentForm.shift_id = data.value?.shifts[0]?.id; assignmentForm.effective_from = today; assignmentForm.effective_to = ''; assignOpen.value = true }
async function createAssignment() {
  if (!assignmentForm.employee_id || !assignmentForm.shift_id) return
  saving.value = true
  try { await api.request('shifts/assignments', { method: 'POST', body: { ...assignmentForm, effective_to: assignmentForm.effective_to || null } }); assignOpen.value = false; toast.add({ title: 'Shift assigned', color: 'success' }); await refresh() } finally { saving.value = false }
}
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Workforce planning
        </p><h2 class="mt-1 text-2xl font-semibold sm:text-3xl">
          Shifts
        </h2><p class="mt-2 text-sm text-muted">
          Configure working hours and maintain the active employee roster.
        </p>
      </div><UButton
        v-if="canManage"
        icon="i-lucide-plus"
        size="lg"
        @click="tab === 'definitions' ? newShift() : newAssignment()"
      >
        {{ tab === 'definitions' ? 'New shift' : 'Assign shift' }}
      </UButton>
    </div><div class="mt-7 flex gap-2 border-b border-[var(--people-border)]">
      <button
        v-for="item in [{ key: 'definitions', label: 'Shift definitions', icon: 'i-lucide-clock-3' }, { key: 'assignments', label: 'Assignments', icon: 'i-lucide-calendar-range' }]"
        :key="item.key"
        class="flex min-h-11 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="tab === item.key ? 'border-primary text-primary' : 'border-transparent text-muted'"
        @click="tab = item.key as typeof tab"
      >
        <UIcon :name="item.icon" />{{ item.label }}
      </button>
    </div><UAlert
      v-if="error"
      class="mt-5"
      color="error"
      variant="soft"
      title="Shift data is unavailable"
      :actions="[{ label: 'Try again', onClick: () => refresh() }]"
    /><div
      v-else-if="pending"
      class="mt-5 grid gap-4 md:grid-cols-2"
    >
      <USkeleton
        v-for="i in 4"
        :key="i"
        class="h-40 rounded-2xl"
      />
    </div><section
      v-else-if="tab === 'definitions'"
      class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <article
        v-for="item in data?.shifts"
        :key="item.id"
        class="people-card p-5"
      >
        <div class="flex items-start justify-between">
          <span class="grid size-11 place-items-center rounded-xl bg-[var(--people-blue)]"><UIcon name="i-lucide-clock-3" /></span><UBadge
            :color="item.is_active ? 'success' : 'neutral'"
            variant="soft"
          >
            {{ item.is_active ? 'Active' : 'Inactive' }}
          </UBadge>
        </div><h3 class="mt-5 text-lg font-semibold">
          {{ item.name }}
        </h3><p class="mt-1 text-sm text-muted">
          {{ item.code || 'No code' }}
        </p><p class="mt-5 text-2xl font-semibold tabular-nums">
          {{ time(item.start_time) }} – {{ time(item.end_time) }}
        </p><div class="mt-3 flex flex-wrap gap-2">
          <UBadge
            color="neutral"
            variant="soft"
          >
            {{ item.break_minutes }}m break
          </UBadge><UBadge
            v-if="item.is_cross_midnight"
            color="info"
            variant="soft"
          >
            Night shift
          </UBadge><UBadge
            v-if="item.enable_auto_attendance"
            color="primary"
            variant="soft"
          >
            Auto attendance
          </UBadge>
        </div>
      </article>
    </section><section
      v-else
      class="people-card mt-5 overflow-hidden"
    >
      <div
        v-if="!data?.assignments.length"
        class="p-12 text-center text-muted"
      >
        No shift assignments found.
      </div><div
        v-else
        class="divide-y divide-[var(--people-border)]"
      >
        <article
          v-for="item in data.assignments"
          :key="item.id"
          class="grid gap-4 p-5 sm:grid-cols-[1fr_1fr_auto] sm:items-center sm:px-6"
        >
          <div>
            <p class="font-semibold">
              {{ item.employee_name || `Employee #${item.employee_id}` }}
            </p><p class="mt-1 text-xs text-muted">
              {{ item.employee_code }}
            </p>
          </div><div>
            <p class="font-medium">
              {{ item.shift_name || `Shift #${item.shift_id}` }}
            </p><p class="mt-1 text-xs text-muted">
              From {{ item.effective_from }}<span v-if="item.effective_to"> to {{ item.effective_to }}</span>
            </p>
          </div><UBadge
            :color="item.status === 'ACTIVE' ? 'success' : 'neutral'"
            variant="soft"
          >
            {{ item.status }}
          </UBadge>
        </article>
      </div>
    </section><USlideover
      v-model:open="createOpen"
      title="Create shift"
    >
      <template #body>
        <form
          id="shift-create"
          class="space-y-5"
          @submit.prevent="createShift"
        >
          <UFormField
            label="Name"
            required
          >
            <UInput
              v-model="shiftForm.name"
              class="w-full"
            />
          </UFormField><UFormField label="Code">
            <UInput
              v-model="shiftForm.code"
              class="w-full"
            />
          </UFormField><UFormField label="Unit">
            <USelect
              v-model="shiftForm.unit_id"
              class="w-full"
              :items="(data?.units || []).map(item => ({ label: item.name, value: item.id }))"
            />
          </UFormField><div class="grid grid-cols-2 gap-4">
            <UFormField label="Starts">
              <UInput
                v-model="shiftForm.start_time"
                class="w-full"
                type="time"
              />
            </UFormField><UFormField label="Ends">
              <UInput
                v-model="shiftForm.end_time"
                class="w-full"
                type="time"
              />
            </UFormField><UFormField label="Grace minutes">
              <UInput
                v-model.number="shiftForm.grace_minutes"
                class="w-full"
                type="number"
              />
            </UFormField><UFormField label="Break minutes">
              <UInput
                v-model.number="shiftForm.break_minutes"
                class="w-full"
                type="number"
              />
            </UFormField>
          </div><UCheckbox
            v-model="shiftForm.enable_auto_attendance"
            label="Enable automatic attendance"
          />
        </form>
      </template><template #footer>
        <UButton
          type="submit"
          form="shift-create"
          block
          :loading="saving"
        >
          Create shift
        </UButton>
      </template>
    </USlideover><USlideover
      v-model:open="assignOpen"
      title="Assign shift"
    >
      <template #body>
        <form
          id="shift-assign"
          class="space-y-5"
          @submit.prevent="createAssignment"
        >
          <UFormField
            label="Employee"
            required
          >
            <USelect
              v-model="assignmentForm.employee_id"
              class="w-full"
              :items="(data?.employees || []).map(item => ({ label: item.full_name || item.employee_code, value: item.id }))"
            />
          </UFormField><UFormField
            label="Shift"
            required
          >
            <USelect
              v-model="assignmentForm.shift_id"
              class="w-full"
              :items="(data?.shifts || []).map(item => ({ label: item.name, value: item.id }))"
            />
          </UFormField><UFormField label="Effective from">
            <UInput
              v-model="assignmentForm.effective_from"
              class="w-full"
              type="date"
            />
          </UFormField><UFormField label="Effective to">
            <UInput
              v-model="assignmentForm.effective_to"
              class="w-full"
              type="date"
            />
          </UFormField>
        </form>
      </template><template #footer>
        <UButton
          type="submit"
          form="shift-assign"
          block
          :loading="saving"
        >
          Assign shift
        </UButton>
      </template>
    </USlideover>
  </div>
</template>
