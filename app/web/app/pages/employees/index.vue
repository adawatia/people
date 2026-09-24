<script setup lang="ts">
import type { Employee, EmployeePage } from '#shared/types/employee'

useSeoMeta({ title: 'Employees' })
const api = useHrmsApi()
const list = useListState({ status: 'ACTIVE', unit_id: '0', department_id: '0', sort_order: 'asc' })
const search = list.search
const status = list.field('status')
const unitId = computed({ get: () => Number(list.field('unit_id').value), set: (value) => {
  void list.update({ unit_id: value, department_id: 0 })
} })
const departmentId = computed({ get: () => Number(list.field('department_id').value), set: (value) => {
  void list.update({ department_id: value })
} })
const { data, pending, error, refresh } = useLazyAsyncData('employees', (_app, { signal }) => api.request<EmployeePage>('employees/', { signal, query: { ...list.query.value, unit_id: unitId.value || undefined, department_id: departmentId.value || undefined, status: status.value === 'ALL' ? undefined : status.value } }), { watch: [list.query, unitId, departmentId, status] })

const initials = (item: Employee) => `${item.first_name[0] || ''}${item.last_name?.[0] || ''}`.toUpperCase()
// Employee records are provisioned and maintained in ERP; this page is read-only.
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
    <UButton
      v-if="list.active.value"
      class="mt-4"
      icon="i-lucide-filter-x"
      variant="outline"
      color="neutral"
      @click="list.clear"
    >
      Clear filters
    </UButton>
    <section class="people-card mt-7 p-4 sm:p-5">
      <div class="grid gap-3 md:grid-cols-4">
        <UInput
          v-model="search"
          icon="i-lucide-search"
          placeholder="Search name, code or email"
          class="md:col-span-2"
        /><RemoteSelect
          v-model="unitId"
          endpoint="org/units"
          label="All units"
        /><USelect
          v-model="status"
          :items="[{ label: 'Active', value: 'ACTIVE' }, { label: 'Inactive', value: 'INACTIVE' }, { label: 'All statuses', value: 'ALL' }]"
        />
      </div><div class="mt-3">
        <RemoteSelect
          v-model="departmentId"
          endpoint="org/departments"
          label="All departments"
          :filters="{ unit_id: unitId || undefined }"
        />
      </div>
    </section>
    <UAlert
      v-if="error"
      class="mt-5"
      color="warning"
      variant="soft"
      icon="i-lucide-coffee"
      title="The people list is taking a short break"
      description="We couldn’t refresh employee details right now. Please try again in a moment."
      :actions="[{ label: 'Refresh people', onClick: () => refresh() }]"
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
          Change your filters or ask an administrator to provision the employee in ERP.
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
      />
    </section>
    <ListPagination
      v-if="data"
      v-model:page="list.page.value"
      v-model:page-size="list.pageSize.value"
      :total="data?.total || 0"
      :total-pages="data?.total_pages"
      :loading="pending"
      label="employees"
    />
  </div>
</template>
