<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
/* eslint-disable @stylistic/max-statements-per-line, vue/multiline-html-element-content-newline, vue/singleline-html-element-content-newline */
import type { Employee, EmployeePage } from '#shared/types/employee'
import type { Department, Designation, Unit } from '#shared/types/organization'

useSeoMeta({ title: 'Employees' })
const api = useHrmsApi()
const auth = useAuth()
const toast = useToast()
const search = ref('')
const debouncedSearch = ref('')
const unitId = ref<number>(0)
const departmentId = ref<number>(0)
const status = ref('ACTIVE')
const page = ref(1)
const createOpen = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ employee_code: '', first_name: '', last_name: '', official_email: '', phone_number: '', unit_id: undefined as number | undefined, department_id: undefined as number | undefined, designation_id: undefined as number | undefined, date_of_joining: '', employment_type: 'PERMANENT', create_user_account: true, username: '', initial_password: '' })
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, (value) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    debouncedSearch.value = value
    page.value = 1
  }, 300)
})
watch([unitId, departmentId, status], () => {
  page.value = 1
})
const { data: masters } = await useAsyncData('employee-masters', async () => {
  const [units, departments, designations] = await Promise.all([api.request<Unit[]>('org/units'), api.request<Department[]>('org/departments'), api.request<Designation[]>('designations/', { query: { is_active: true } })])
  return { units, departments, designations }
})
const { data, pending, error, refresh } = await useAsyncData('employees', () => api.request<EmployeePage>('employees/', { query: { page: page.value, page_size: 20, q: debouncedSearch.value || undefined, unit_id: unitId.value || undefined, department_id: departmentId.value || undefined, status: status.value === 'ALL' ? undefined : status.value } }), { watch: [page, debouncedSearch, unitId, departmentId, status] })
const departments = computed(() => (masters.value?.departments || []).filter(item => !unitId.value || item.unit_id === unitId.value))
const initials = (item: Employee) => `${item.first_name[0] || ''}${item.last_name?.[0] || ''}`.toUpperCase()
function resetForm() {
  editingId.value = null
  Object.assign(form, { employee_code: '', first_name: '', last_name: '', official_email: '', phone_number: '', unit_id: undefined, department_id: undefined, designation_id: undefined, date_of_joining: '', employment_type: 'PERMANENT', create_user_account: true, username: '', initial_password: '' })
  createOpen.value = true
}
function editEmployee(item: Employee) {
  editingId.value = item.id
  Object.assign(form, { employee_code: item.employee_code, first_name: item.first_name, last_name: item.last_name || '', official_email: item.official_email || '', phone_number: item.phone_number || '', unit_id: item.unit_id || undefined, department_id: item.department_id || undefined, designation_id: item.designation_id || undefined, date_of_joining: item.date_of_joining || '', employment_type: item.employment_type })
  createOpen.value = true
}
async function saveEmployee() {
  if (!form.employee_code.trim() || !form.first_name.trim()) return
  saving.value = true
  try {
    const body = { ...form, employee_code: form.employee_code.trim(), first_name: form.first_name.trim(), last_name: form.last_name.trim() || null, official_email: form.official_email.trim() || null, phone_number: form.phone_number.trim() || null, date_of_joining: form.date_of_joining || null }
    await api.request(editingId.value ? `employees/${editingId.value}` : 'employees/onboard', { method: editingId.value ? 'PATCH' : 'POST', body: editingId.value ? Object.fromEntries(Object.entries(body).filter(([key]) => !['employee_code', 'create_user_account', 'username'].includes(key))) : body })
    createOpen.value = false
    toast.add({ title: `Employee ${editingId.value ? 'updated' : 'created'}`, color: 'success', icon: 'i-lucide-user-round-check' })
    await refresh()
  } catch (saveError) {
    const candidate = saveError as { data?: { detail?: string, statusMessage?: string } }
    toast.add({ title: 'Could not save employee', description: candidate.data?.detail || candidate.data?.statusMessage, color: 'error' })
  } finally { saving.value = false }
}
async function toggleEmployee(item: Employee) {
  try {
    await api.request(`employees/${item.id}/${item.status === 'ACTIVE' ? 'deactivate' : 'activate'}`, { method: 'PATCH' })
    toast.add({ title: `${item.full_name || item.employee_code} ${item.status === 'ACTIVE' ? 'deactivated' : 'activated'}`, color: 'success' })
    await refresh()
  } catch (toggleError) { const candidate = toggleError as { data?: { detail?: string, statusMessage?: string } }; toast.add({ title: 'Could not change employee status', description: candidate.data?.detail || candidate.data?.statusMessage, color: 'error' }) }
}
async function deleteEmployee(item: Employee) {
  if (!confirm(`Delete ${item.full_name || item.employee_code}? This cannot be undone.`)) return
  try { await api.request(`employees/${item.id}`, { method: 'DELETE' }); toast.add({ title: 'Employee deleted', color: 'success' }); await refresh() } catch (deleteError) { const candidate = deleteError as { data?: { detail?: string, statusMessage?: string } }; toast.add({ title: 'Could not delete employee', description: candidate.data?.detail || candidate.data?.statusMessage, color: 'error' }) }
}
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          People directory
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Employees
        </h2><p class="mt-2 text-sm text-muted">
          Find people, understand reporting context, and manage employment records.
        </p>
      </div><UAlert
        class="max-w-md"
        color="info"
        variant="soft"
        icon="i-lucide-database"
        title="Employee records are managed by ERP"
        description="Create or provision employees in ERP. Changes will sync here automatically."
      />
    </div>
    <section class="people-card mt-7 p-4 sm:p-5">
      <div class="grid gap-3 md:grid-cols-4">
        <UInput
          v-model="search"
          icon="i-lucide-search"
          placeholder="Search name, code or email"
          class="md:col-span-2"
        /><USelect
          v-model="unitId"
          :items="[{ label: 'All units', value: 0 }, ...(masters?.units || []).map(item => ({ label: item.name, value: item.id }))]"
          placeholder="All units"
        /><USelect
          v-model="status"
          :items="[{ label: 'Active', value: 'ACTIVE' }, { label: 'Inactive', value: 'INACTIVE' }, { label: 'All statuses', value: 'ALL' }]"
        />
      </div><div class="mt-3">
        <USelect
          v-model="departmentId"
          :items="[{ label: 'All departments', value: 0 }, ...departments.map(item => ({ label: item.name, value: item.id }))]"
          placeholder="All departments"
          class="w-full md:w-64"
        />
      </div>
    </section>
    <UAlert
      v-if="error"
      class="mt-5"
      color="error"
      variant="soft"
      title="Employees are unavailable"
      :actions="[{ label: 'Try again', onClick: () => refresh() }]"
    />
    <section class="people-card mt-5 overflow-hidden">
      <div class="flex items-center justify-between border-b border-[var(--people-border)] px-5 py-4">
        <p class="text-sm text-muted">
          <span class="font-semibold text-highlighted">{{ data?.total || 0 }}</span> employees
        </p><p class="text-xs text-muted">
          Page {{ data?.page || 1 }} of {{ data?.total_pages || 1 }}
        </p>
      </div>
      <div
        v-if="pending"
        class="space-y-3 p-5"
      >
        <USkeleton
          v-for="i in 7"
          :key="i"
          class="h-16 w-full"
        />
      </div>
      <div
        v-else-if="!data?.items.length"
        class="p-12 text-center"
      >
        <UIcon
          name="i-lucide-users-round"
          class="mx-auto size-10 text-muted"
        /><h3 class="mt-4 font-semibold">
          No employees found
        </h3><p class="mt-1 text-sm text-muted">
          Change your filters or add the first employee.
        </p>
      </div>
      <div v-else>
        <div class="divide-y divide-[var(--people-border)] md:hidden">
          <NuxtLink
            v-for="item in data.items"
            :key="item.id"
            :to="`/employees/${item.id}`"
            class="flex gap-3 p-4"
          ><UAvatar :text="initials(item)" /><div class="min-w-0 flex-1"><div class="flex items-start justify-between gap-3"><p class="truncate font-semibold">{{ item.full_name || `${item.first_name} ${item.last_name || ''}` }}</p><UBadge
            :color="item.status === 'ACTIVE' ? 'success' : 'neutral'"
            variant="soft"
            size="sm"
          >{{ item.status }}</UBadge></div><p class="mt-1 truncate text-sm text-muted">{{ item.designation_name || 'No designation' }} · {{ item.employee_code }}</p><p class="mt-1 truncate text-xs text-muted">{{ item.department_name || 'No department' }} · {{ item.unit_name || 'No unit' }}</p></div></NuxtLink>
        </div>
        <div class="hidden overflow-x-auto md:block">
          <table class="w-full min-w-[780px] text-left text-sm">
            <thead class="bg-muted/5 text-xs uppercase tracking-wide text-muted">
              <tr>
                <th class="px-6 py-3">
                  Employee
                </th><th class="px-4 py-3">
                  Role
                </th><th class="px-4 py-3">
                  Organization
                </th><th class="px-4 py-3">
                  Type
                </th><th class="px-6 py-3 text-right">
                  Status
                </th>
              </tr>
            </thead><tbody class="divide-y divide-[var(--people-border)]">
              <tr
                v-for="item in data.items"
                :key="item.id"
                class="hover:bg-muted/5"
              >
                <td class="px-6 py-4">
                  <NuxtLink
                    :to="`/employees/${item.id}`"
                    class="flex items-center gap-3"
                  ><UAvatar :text="initials(item)" /><span><span class="block font-semibold">{{ item.full_name || `${item.first_name} ${item.last_name || ''}` }}</span><span class="mt-0.5 block text-xs text-muted">{{ item.employee_code }} · {{ item.official_email || 'No email' }}</span></span></NuxtLink>
                </td><td class="px-4 py-4">
                  {{ item.designation_name || '—' }}
                </td><td class="px-4 py-4">
                  <span class="block">{{ item.department_name || '—' }}</span><span class="text-xs text-muted">{{ item.unit_name }}</span>
                </td><td class="px-4 py-4">
                  {{ item.employment_type }}
                </td><td class="px-4 py-4 text-right">—
                </td><td class="px-6 py-4 text-right">
                  <UBadge
                    :color="item.status === 'ACTIVE' ? 'success' : 'neutral'"
                    variant="soft"
                  >
                    {{ item.status }}
                  </UBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div
        v-if="(data?.total_pages || 1) > 1"
        class="flex justify-end border-t border-[var(--people-border)] p-4"
      >
        <UPagination
          v-model:page="page"
          :total="data?.total || 0"
          :items-per-page="20"
        />
      </div>
    </section>
    <USlideover
      v-model:open="createOpen"
      :title="`${editingId ? 'Edit' : 'Add'} employee`"
      description="Create the core employment record."
    >
      <template #body>
        <form
          id="employee-create"
          class="space-y-5"
          @submit.prevent="saveEmployee"
        >
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField
              label="Employee code"
              required
            >
              <UInput
                v-model="form.employee_code"
                class="w-full"
                :disabled="!!editingId"
              />
            </UFormField><UFormField label="Employment type">
              <USelect
                v-model="form.employment_type"
                class="w-full"
                :items="['PERMANENT', 'CONTRACT', 'INTERN', 'TEMPORARY']"
              />
            </UFormField><UFormField
              label="First name"
              required
            >
              <UInput
                v-model="form.first_name"
                class="w-full"
              />
            </UFormField><UFormField label="Last name">
              <UInput
                v-model="form.last_name"
                class="w-full"
              />
            </UFormField>
          </div><UFormField label="Official email">
            <UInput
              v-model="form.official_email"
              class="w-full"
              type="email"
            />
          </UFormField><UFormField label="Phone">
            <UInput
              v-model="form.phone_number"
              class="w-full"
            />
          </UFormField><UFormField label="Unit">
            <USelect
              v-model="form.unit_id"
              class="w-full"
              :items="(masters?.units || []).map(item => ({ label: item.name, value: item.id }))"
            />
          </UFormField><UFormField label="Department">
            <USelect
              v-model="form.department_id"
              class="w-full"
              :items="(masters?.departments || []).filter(item => !form.unit_id || item.unit_id === form.unit_id).map(item => ({ label: item.name, value: item.id }))"
            />
          </UFormField><UFormField label="Designation">
            <USelect
              v-model="form.designation_id"
              class="w-full"
              :items="(masters?.designations || []).map(item => ({ label: item.name, value: item.id }))"
            />
          </UFormField><UFormField label="Joining date">
            <UInput
              v-model="form.date_of_joining"
              class="w-full"
              type="date"
            />
          </UFormField>
          <div v-if="!editingId" class="rounded-lg border border-[var(--people-border)] bg-muted/5 p-4 sm:col-span-2">
            <UCheckbox v-model="form.create_user_account" label="Create portal login account" />
            <p class="mt-1 text-xs text-muted">The employee will receive a temporary password and must change it after first login.</p>
            <div v-if="form.create_user_account" class="mt-4 grid gap-4 sm:grid-cols-2">
              <UFormField label="Username (optional)">
                <UInput v-model="form.username" class="w-full" placeholder="Defaults to email prefix" />
              </UFormField>
              <UFormField label="Initial password" required>
                <UInput
                  v-model="form.initial_password"
                  class="w-full"
                  type="password"
                  autocomplete="new-password"
                  placeholder="Temporary password"
                />
                <template #help>
                  The employee must change this password after first login.
                </template>
              </UFormField>
            </div>
          </div>
        </form>
      </template><template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            color="neutral"
            variant="ghost"
            @click="createOpen = false"
          >
            Cancel
          </UButton><UButton
            type="submit"
            form="employee-create"
            :loading="saving"
          >
            {{ editingId ? 'Save changes' : 'Create employee' }}
          </UButton>
        </div>
      </template>
    </USlideover>
  </div>
</template>
