<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { Shift, ShiftAssignment } from '#shared/types/workforce'

useSeoMeta({ title: 'Shifts' })
const api = useHrmsApi()
const list = useListState({ sort_order: 'desc' })
const tab = ref<'definitions' | 'assignments'>('definitions')
// Shift definitions and employee assignments are authored in ERP and mirrored here.
const { data, pending, error, refresh } = await useAsyncData('shift-workspace', async () => {
  const [shifts, assignments] = await Promise.all([api.request<PaginatedResponse<Shift>>('shifts/', { query: { ...list.query.value, is_active: true } }), api.request<PaginatedResponse<ShiftAssignment>>('shifts/assignments', { query: list.query.value })])
  return { shifts: shifts.items, shiftPage: shifts, assignments: assignments.items, assignmentPage: assignments }
}, { watch: [list.query] })
const time = (value: string) => value?.slice(0, 5) || '—'
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
          Review the shift definitions and employee assignments synchronized from ERP.
        </p>
      </div>
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
    </div>
    <ListControls
      v-if="tab === 'assignments'"
      v-model:search="list.search.value"
      :active="list.active.value"
      search-placeholder="Search employee name or code"
      @clear="list.clear"
    />
    <UAlert
      v-if="error"
      class="mt-5"
      color="warning"
      variant="soft"
      icon="i-lucide-coffee"
      title="Your shifts are taking a short break"
      description="We couldn’t refresh shift details right now. Please try again in a moment."
      :actions="[{ label: 'Refresh shifts', onClick: () => refresh() }]"
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
    </section>
    <ListPagination
      v-if="data"
      v-model:page="list.page.value"
      v-model:page-size="list.pageSize.value"
      :total="tab === 'assignments' ? data.assignmentPage.total : data.shiftPage.total"
      :loading="pending"
    />
  </div>
</template>
