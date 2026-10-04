<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { Employee, EmployeeWorkHistory } from '#shared/types/employee'

const route = useRoute()
const api = useHrmsApi()
const list = useListState({ sort_order: 'desc' })
const employeeId = computed(() => Number(route.params.id))
const { data: rawData, pending, error, refresh } = await useAsyncData(`employee-${employeeId.value}`, async () => {
  const [employee, history] = await Promise.all([api.request<Employee>(`employees/${employeeId.value}`), api.request<PaginatedResponse<EmployeeWorkHistory>>(`employees/${employeeId.value}/work-history`, { query: list.query.value })])
  return { employee, history }
}, { watch: [list.query, employeeId] })
const data = useRetainedData(rawData)
useSeoMeta({ title: () => data.value?.employee.full_name || 'Employee profile' })
const initials = computed(() => `${data.value?.employee.first_name?.[0] || ''}${data.value?.employee.last_name?.[0] || ''}`.toUpperCase())
const formatDate = (value?: string | null) => value ? new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${value}T00:00:00`)) : '—'
</script>

<template>
  <div class="people-page">
    <DataFeedback
      :pending="pending"
      :error="error"
      :has-data="Boolean(data)"
    />
    <UButton
      to="/employees"
      color="neutral"
      variant="ghost"
      icon="i-lucide-arrow-left"
    >
      Employees
    </UButton>
    <UAlert
      v-if="error"
      class="mt-5"
      color="warning"
      variant="soft"
      icon="i-lucide-circle-alert"
      title="Updates could not be loaded"
      description="We couldn’t refresh the profile right now. Please try again in a moment."
      :actions="[{ label: 'Refresh profile', onClick: () => refresh() }]"
    />
    <div
      v-if="pending && !data"
      class="mt-5 space-y-5"
    >
      <USkeleton class="h-48 rounded-2xl" /><USkeleton class="h-64 rounded-2xl" />
    </div>
    <template v-else-if="data">
      <section class="people-card mt-5 overflow-hidden">
        <div class="px-5 pb-6 sm:px-7">
          <div class="py-5 flex flex-col gap-4 sm:flex-row sm:items-end">
            <UAvatar
              :text="initials"
              size="3xl"
              class="ring-4 ring-[var(--people-surface)]"
            /><div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-3">
                <h1 class="text-2xl font-semibold">
                  {{ data.employee.full_name || `${data.employee.first_name} ${data.employee.last_name || ''}` }}
                </h1><UBadge
                  :color="data.employee.status === 'ACTIVE' ? 'success' : 'neutral'"
                  variant="soft"
                >
                  {{ data.employee.status }}
                </UBadge>
              </div><p class="mt-1 text-sm text-muted">
                {{ data.employee.designation_name || 'No designation' }} · {{ data.employee.employee_code }}
              </p>
            </div>
          </div>
        </div>
      </section>
      <div class="mt-5 grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <section class="people-card p-5 sm:p-6">
          <h3 class="font-semibold">
            Employment information
          </h3><dl class="mt-5 grid gap-5 sm:grid-cols-2">
            <div>
              <dt class="text-xs font-medium uppercase tracking-wide text-muted">
                Unit
              </dt><dd class="mt-1 font-medium">
                {{ data.employee.unit_name || '—' }}
              </dd>
            </div><div>
              <dt class="text-xs font-medium uppercase tracking-wide text-muted">
                Department
              </dt><dd class="mt-1 font-medium">
                {{ data.employee.department_name || '—' }}
              </dd>
            </div><div>
              <dt class="text-xs font-medium uppercase tracking-wide text-muted">
                Reporting manager
              </dt><dd class="mt-1 font-medium">
                {{ data.employee.reporting_manager_name || '—' }}
              </dd>
            </div><div>
              <dt class="text-xs font-medium uppercase tracking-wide text-muted">
                Employment type
              </dt><dd class="mt-1 font-medium">
                {{ data.employee.employment_type }}
              </dd>
            </div><div>
              <dt class="text-xs font-medium uppercase tracking-wide text-muted">
                Joining date
              </dt><dd class="mt-1 font-medium">
                {{ formatDate(data.employee.date_of_joining) }}
              </dd>
            </div>
          </dl>
        </section>
        <section class="people-card p-5 sm:p-6">
          <h3 class="font-semibold">
            Contact
          </h3><div class="mt-5 space-y-4">
            <div class="flex gap-3">
              <UIcon
                name="i-lucide-mail"
                class="mt-0.5 size-5 text-muted"
              /><div>
                <p class="text-xs text-muted">
                  Official email
                </p><p class="mt-1 break-all text-sm font-medium">
                  {{ data.employee.official_email || '—' }}
                </p>
              </div>
            </div><div class="flex gap-3">
              <UIcon
                name="i-lucide-phone"
                class="mt-0.5 size-5 text-muted"
              /><div>
                <p class="text-xs text-muted">
                  Phone
                </p><p class="mt-1 text-sm font-medium">
                  {{ data.employee.phone_number || '—' }}
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
      <section class="people-card mt-5 overflow-hidden">
        <div class="border-b border-[var(--people-border)] p-5 sm:px-6">
          <h3 class="font-semibold">
            Work history
          </h3><p class="mt-1 text-sm text-muted">
            Organization and designation changes over time
          </p>
        </div><div
          v-if="!data.history.items.length"
          class="p-8 text-center text-sm text-muted"
        >
          No work history recorded.
        </div><div
          v-else
          class="divide-y divide-[var(--people-border)]"
        >
          <article
            v-for="item in data.history.items"
            :key="item.id"
            class="flex gap-4 p-5 sm:px-6"
          >
            <span class="mt-1 size-3 shrink-0 rounded-full bg-primary ring-4 ring-primary/10" /><div>
              <p class="font-medium">
                {{ formatDate(item.from_date) }} – {{ item.to_date ? formatDate(item.to_date) : 'Present' }}
              </p><p class="mt-1 text-sm text-muted">
                {{ item.remarks || 'Employment assignment' }}
              </p>
            </div>
          </article>
        </div>
      </section>
      <ListControls
        v-model:search="list.search.value"
        v-model:sort-by="list.sortBy.value"
        v-model:sort-order="list.sortOrder.value"
        :active="list.active.value"
        :sorts="[{ label: 'Start date', value: 'from_date' }, { label: 'End date', value: 'to_date' }, { label: 'Recorded', value: 'created_at' }]"
        search-placeholder="Search work-history notes"
        @clear="list.clear"
      />
    </template>
    <ListPagination
      v-if="data?.history"
      v-model:page="list.page.value"
      v-model:page-size="list.pageSize.value"
      :total="data?.history?.total || 0"
      :total-pages="data?.history?.total_pages"
      :loading="pending"
    />
  </div>
</template>
