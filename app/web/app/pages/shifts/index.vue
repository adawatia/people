<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { Shift, ShiftAssignment } from '#shared/types/workforce'

useSeoMeta({ title: 'Shifts' })
const api = useHrmsApi()
const auth = useAuth()
const workspace = useWorkspace()
const definitionList = useListState({ sort_order: 'asc' }, 'shift_')
const assignmentList = useListState({ sort_order: 'desc' }, 'assignment_')
const tab = ref<'definitions' | 'assignments'>('definitions')
// Shift definitions and employee assignments are authored in ERP and mirrored here.
const activeQuery = computed(() => JSON.stringify({
  tab: tab.value,
  query: tab.value === 'definitions'
    ? definitionList.query.value
    : { ...assignmentList.query.value, employee_id: workspace.current.value === 'MY' ? auth.user.value?.employee_id : undefined }
}))
const dataKey = computed(() => `shift-workspace:${auth.user.value?.id ?? 'guest'}:${workspace.current.value}`)
const { data: rawData, pending, error, refresh } = useLazyAsyncData(dataKey, async (_app, { signal }) => {
  const selectedTab = tab.value
  const employee_id = workspace.current.value === 'MY' ? auth.user.value?.employee_id : undefined
  if (selectedTab === 'definitions') {
    const shifts = await api.request<PaginatedResponse<Shift>>('shifts/', {
      signal, query: { ...definitionList.query.value, is_active: true }
    })
    return { tab: selectedTab, shifts: shifts.items, shiftPage: shifts, assignments: [] as ShiftAssignment[], assignmentPage: null as PaginatedResponse<ShiftAssignment> | null }
  }
  const assignments = await api.request<PaginatedResponse<ShiftAssignment>>('shifts/assignments', {
    signal, query: { ...assignmentList.query.value, employee_id }
  })
  return { tab: selectedTab, shifts: [] as Shift[], shiftPage: null as PaginatedResponse<Shift> | null, assignments: assignments.items, assignmentPage: assignments }
}, { watch: [activeQuery, workspace.current] })
const retainedData = useRetainedData(rawData)
const data = computed(() => retainedData.value?.tab === tab.value ? retainedData.value : null)
const time = (value: string) => value?.slice(0, 5) || '—'
const scopeDescription = computed(() => workspace.current.value === 'MY'
  ? 'Review only your assigned shift and schedule history synchronized from ERP.'
  : workspace.current.value === 'TEAM'
    ? 'Review shift assignments for employees in your department.'
    : 'Review shift assignments for employees in your authorized HR scope.')
</script>

<template>
  <div class="people-page">
    <DataFeedback
      :pending="pending"
      :error="error"
      :has-data="Boolean(data)"
    />
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 class="mt-1 text-2xl font-semibold sm:text-3xl">
          Shifts
        </h1><p class="mt-2 text-sm text-muted">
          {{ scopeDescription }}
        </p>
      </div>
    </div><div
      data-page-tabs
      role="tablist"
      aria-label="Shift management sections"
      class="mt-7 flex gap-2 border-b border-[var(--people-border)]"
    >
      <button
        v-for="item in [{ key: 'definitions', label: 'Shift definitions', icon: 'i-lucide-clock-3' }, { key: 'assignments', label: 'Assignments', icon: 'i-lucide-calendar-range' }]"
        :key="item.key"
        class="flex min-h-11 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="tab === item.key ? 'border-primary text-primary' : 'border-transparent text-muted'"
        role="tab"
        :aria-selected="tab === item.key"
        @click="tab = item.key as typeof tab"
      >
        <UIcon :name="item.icon" />{{ item.label }}
      </button>
    </div>
    <ListControls
      v-if="tab === 'definitions'"
      v-model:search="definitionList.search.value"
      v-model:sort-by="definitionList.sortBy.value"
      v-model:sort-order="definitionList.sortOrder.value"
      :active="definitionList.active.value"
      :sorts="[{ label: 'Name', value: 'name' }, { label: 'Code', value: 'code' }, { label: 'Start time', value: 'start_time' }]"
      search-placeholder="Search shift definitions"
      @clear="definitionList.clear"
    />
    <ListControls
      v-else
      v-model:search="assignmentList.search.value"
      v-model:sort-by="assignmentList.sortBy.value"
      v-model:sort-order="assignmentList.sortOrder.value"
      :active="assignmentList.active.value"
      :sorts="[{ label: 'Effective date', value: 'effective_from' }, { label: 'Status', value: 'status' }]"
      search-placeholder="Search employee name or code"
      @clear="assignmentList.clear"
    />
    <UAlert
      v-if="error"
      class="mt-5"
      color="warning"
      variant="soft"
      icon="i-lucide-circle-alert"
      title="Updates could not be loaded"
      description="We couldn’t refresh shift details right now. Please try again in a moment."
      :actions="[{ label: 'Refresh shifts', onClick: () => refresh() }]"
    /><div
      v-if="pending && !data"
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
      <ListEmptyState
        v-if="!pending && !error && !data?.assignments.length"
        title="No shift assignments found"
        description="Assigned schedules appear here after they are synchronized from ERP."
        :filtered="assignmentList.active.value"
        @reset="assignmentList.clear"
      /><div
        v-if="data?.assignments.length"
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
    </section>
    <ListEmptyState
      v-if="tab === 'definitions' && !pending && !error && !data?.shifts.length"
      title="No shift definitions available"
      description="Active shift definitions appear here after they are synchronized from ERP."
    />
    <ListPagination
      v-if="data && tab === 'definitions'"
      v-model:page="definitionList.page.value"
      v-model:page-size="definitionList.pageSize.value"
      :total="data.shiftPage?.total || 0"
      :loading="pending"
    />
    <ListPagination
      v-else-if="data"
      v-model:page="assignmentList.page.value"
      v-model:page-size="assignmentList.pageSize.value"
      :total="data.assignmentPage?.total || 0"
      :loading="pending"
    />
  </div>
</template>
