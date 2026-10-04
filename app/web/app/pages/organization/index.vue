<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { Department, Designation, Organization, Unit } from '#shared/types/organization'

type Tab = 'units' | 'departments' | 'designations'
useSeoMeta({ title: 'Organization' })
const api = useHrmsApi()
const list = useListState({ tab: 'units', sort_order: 'asc' })
const activeTab = list.field('tab')
const { data: organization, pending: organizationPending, error: organizationError, refresh: refreshOrganization } = await useAsyncData(
  'organization-profile',
  () => api.request<Organization>('org/organization')
)
const organizationDetails = computed(() => {
  if (!organization.value) return []
  return [
    { label: 'Organization name', value: organization.value.name },
    { label: 'Organization code', value: organization.value.short_name },
    { label: 'ERP ID', value: organization.value.erp_id },
    { label: 'Industry', value: organization.value.industry },
    { label: 'Address line 1', value: organization.value.address_line1 },
    { label: 'Address line 2', value: organization.value.address_line2 },
    { label: 'City', value: organization.value.city },
    { label: 'State', value: organization.value.state },
    { label: 'Country', value: organization.value.country },
    { label: 'Postal code', value: organization.value.postal_code },
    { label: 'Phone', value: organization.value.phone },
    { label: 'Email', value: organization.value.email },
    { label: 'Website', value: organization.value.website },
    { label: 'Tax ID', value: organization.value.tax_id },
    { label: 'Created', value: formatDateTime(organization.value.created_at) },
    { label: 'Last updated', value: organization.value.updated_at ? formatDateTime(organization.value.updated_at) : null }
  ]
})
const organizationDetailsAccordion = [{
  label: 'Show organization details',
  icon: 'i-lucide-list',
  value: 'organization-details',
  content: 'Organization details'
}]
function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Kolkata'
  }).format(new Date(value))
}
const { data: rawData, pending, error, refresh } = await useAsyncData('organization-workspace', async (_app, { signal }) => {
  const endpoint = activeTab.value === 'units' ? 'org/units' : activeTab.value === 'departments' ? 'org/departments' : 'designations/'
  const result = await api.request<PaginatedResponse<Unit | Department | Designation>>(endpoint, { signal, query: list.query.value })
  return { ...result, units: activeTab.value === 'units' ? result.items as Unit[] : [], departments: activeTab.value === 'departments' ? result.items as Department[] : [], designations: activeTab.value === 'designations' ? result.items as Designation[] : [] }
}, { watch: [activeTab, list.query] })
const data = useRetainedData(rawData)
function unitName(id: number) {
  return `Unit #${id}`
}
// Structure writes are ERP-owned: this page only reads and renders master data.
</script>

<template>
  <div class="people-page">
    <DataFeedback
      :pending="pending"
      :error="error"
      :has-data="Boolean(data)"
    />
    <header class="my-6">
      <p class="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
        Organization profile
      </p>
      <div
        v-if="organization"
        class="people-card mt-3 flex flex-wrap items-center justify-between gap-5 p-5 sm:p-6"
      >
        <div class="flex min-w-0 items-center gap-4">
          <span class="grid size-12 shrink-0 place-items-center rounded-2xl bg-[var(--people-lavender)] text-[var(--people-lavender-ink)] sm:size-14">
            <UIcon
              name="i-lucide-building-2"
              class="size-6 sm:size-7"
            />
          </span>
          <div class="min-w-0">
            <h1 class="truncate text-2xl font-semibold sm:text-3xl">
              {{ organization.name }}
            </h1>
            <p class="mt-1 text-sm text-muted">
              Company structure · Read-only ERP data
            </p>
          </div>
        </div>
        <div class="shrink-0 rounded-xl border border-[var(--people-border)] bg-[var(--people-canvas)] px-4 py-3">
          <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
            Organization code
          </p>
          <p class="mt-1 font-mono text-sm font-semibold text-[var(--people-text)]">
            {{ organization.short_name || 'Not assigned' }}
          </p>
        </div>
      </div>
      <div
        v-else-if="organizationPending"
        class="people-card mt-3 flex items-center gap-4 p-5 sm:p-6"
        aria-label="Loading organization profile"
      >
        <USkeleton class="size-12 rounded-2xl sm:size-14" />
        <div class="grid min-w-0 flex-1 gap-2">
          <USkeleton class="h-7 w-2/3" />
          <USkeleton class="h-4 w-1/3" />
        </div>
      </div>
      <UAlert
        v-else-if="organizationError"
        class="mt-3"
        color="warning"
        variant="soft"
        icon="i-lucide-circle-alert"
        title="Organization profile unavailable"
        description="The organization name and code could not be loaded."
        :actions="[{ label: 'Retry', onClick: () => refreshOrganization() }]"
      />
      <p class="mt-3 text-sm text-muted">
        Units, departments and designations are maintained in ERP.
      </p>
    </header>
    <section
      v-if="organization"
      class="people-card mt-5 p-3 sm:p-4"
      aria-label="Organization details"
    >
      <UAccordion
        :items="organizationDetailsAccordion"
        :ui="{ item: 'border-0', trigger: 'rounded-xl px-4 py-3', content: 'px-4', body: 'p-0 pb-1' }"
      >
        <template #content>
          <dl class="grid gap-x-8 gap-y-5 pb-2 pt-2 sm:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="detail in organizationDetails"
              :key="detail.label"
              class="min-w-0 border-t border-[var(--people-border)] pt-3"
            >
              <dt class="text-xs font-semibold uppercase tracking-[0.08em] text-muted">
                {{ detail.label }}
              </dt>
              <dd class="mt-1 break-words text-sm font-medium">
                {{ detail.value || 'Not provided' }}
              </dd>
            </div>
          </dl>
        </template>
      </UAccordion>
    </section>
    <div
      data-page-tabs
      class="mt-7 flex gap-2 overflow-x-auto border-b border-[var(--people-border)]"
    >
      <button
        v-for="tab in [{ key: 'units', label: 'Units', icon: 'i-lucide-building-2' }, { key: 'departments', label: 'Departments', icon: 'i-lucide-network' }, { key: 'designations', label: 'Designations', icon: 'i-lucide-badge' }]"
        :key="tab.key"
        class="flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="activeTab === tab.key ? 'border-primary text-primary' : 'border-transparent text-muted'"
        :aria-pressed="activeTab === tab.key"
        @click="activeTab = tab.key as Tab"
      >
        <UIcon :name="tab.icon" />{{ tab.label }}
      </button>
    </div>
    <ListControls
      v-model:search="list.search.value"
      v-model:sort-by="list.sortBy.value"
      v-model:sort-order="list.sortOrder.value"
      :active="list.active.value"
      :sorts="[{ label: 'Name', value: 'name' }, { label: 'Newest', value: 'id' }]"
      :search-placeholder="`Search ${activeTab}`"
      @clear="list.clear"
    />
    <UAlert
      v-if="error"
      class="mt-5"
      color="warning"
      variant="soft"
      icon="i-lucide-circle-alert"
      title="Updates could not be loaded"
      description="We couldn’t refresh these details right now. Please try again in a moment."
      :actions="[{ label: 'Refresh details', onClick: () => refresh() }]"
    />
    <div
      v-if="pending && !data"
      class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <USkeleton
        v-for="i in 6"
        :key="i"
        class="h-40 rounded-2xl"
      />
    </div>
    <section
      v-else-if="activeTab === 'units'"
      class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <article
        v-for="item in data?.units"
        :key="item.id"
        class="people-card p-5"
      >
        <div class="flex items-start justify-between">
          <span class="grid size-11 place-items-center rounded-xl bg-[var(--people-blue)]"><UIcon
            name="i-lucide-building-2"
            class="size-5"
          /></span><UBadge
            :color="item.is_active ? 'success' : 'neutral'"
            variant="soft"
          >
            {{ item.is_active ? 'Active' : 'Inactive' }}
          </UBadge>
        </div><h3 class="mt-5 text-lg font-semibold">
          {{ item.name }}
        </h3><p class="mt-1 text-sm text-muted">
          {{ item.code || 'No code' }}<span v-if="item.city"> · {{ item.city }}</span>
        </p><div class="mt-5 flex items-center gap-2 text-sm text-muted">
          <UIcon name="i-lucide-network" />Unit
        </div>
      </article>
    </section>
    <section
      v-else-if="activeTab === 'departments'"
      class="people-card mt-5 overflow-hidden"
    >
      <div class="divide-y divide-[var(--people-border)]">
        <article
          v-for="item in data?.departments"
          :key="item.id"
          class="flex items-center gap-4 p-5 sm:px-6"
        >
          <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-[var(--people-mint)]"><UIcon name="i-lucide-network" /></span><div class="min-w-0 flex-1">
            <h3 class="break-words font-semibold">
              {{ item.name }}
            </h3><p class="mt-1 text-sm text-muted">
              {{ unitName(item.unit_id) }} · {{ item.code || 'No code' }}
            </p>
          </div><UBadge
            :color="item.is_active ? 'success' : 'neutral'"
            variant="soft"
          >
            {{ item.is_active ? 'Active' : 'Inactive' }}
          </UBadge>
        </article>
      </div>
    </section>
    <section
      v-else
      class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <article
        v-for="item in data?.designations"
        :key="item.id"
        class="people-card p-5"
      >
        <div class="flex items-start justify-between">
          <span class="grid size-10 place-items-center rounded-xl bg-[var(--people-forest)]"><UIcon name="i-lucide-badge" /></span><UBadge
            :color="item.is_active ? 'success' : 'neutral'"
            variant="soft"
          >
            {{ item.is_active ? 'Active' : 'Inactive' }}
          </UBadge>
        </div><h3 class="mt-5 font-semibold">
          {{ item.name }}
        </h3><p class="mt-1 text-xs font-semibold uppercase tracking-wide text-muted">
          {{ item.code || 'No code' }}
        </p><p class="mt-3 text-sm text-muted">
          {{ item.description || 'No description provided.' }}
        </p><p class="mt-4 flex items-center justify-end gap-2 text-xs text-muted">
          <UIcon name="i-lucide-refresh-cw" />Managed by ERP
        </p>
      </article>
    </section>
    <ListEmptyState
      v-if="!pending && !error && !data?.total"
      title="No organization records found"
      description="Organization structure is synchronized from ERP."
      :filtered="list.active.value"
      @reset="list.clear"
    />
    <ListPagination
      v-if="data"
      v-model:page="list.page.value"
      v-model:page-size="list.pageSize.value"
      :total="data.total"
      :loading="pending"
    />
  </div>
</template>
