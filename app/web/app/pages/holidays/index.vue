<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { HolidayList } from '#shared/types/workforce'

useSeoMeta({ title: 'Holidays' })
const api = useHrmsApi()
const list = useListState({ sort_order: 'asc' })
const selectedId = ref<number>()
// Holiday calendars are ERP-owned; the UI is display-only.
const { data, pending, error, refresh } = await useAsyncData('holiday-workspace', async () => {
  const lists = await api.request<PaginatedResponse<HolidayList>>('holidays/lists', { query: list.query.value })
  return { lists: lists.items, ...lists }
}, { watch: [list.query] })
watchEffect(() => {
  if (!data.value?.lists.some(item => item.id === selectedId.value) && data.value?.lists[0]) selectedId.value = data.value.lists[0].id
})
const selected = computed(() => data.value?.lists.find(item => item.id === selectedId.value))
const formatDate = (value: string) => new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(`${value}T00:00:00`))
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Work calendar
        </p><h2 class="mt-1 text-2xl font-semibold sm:text-3xl">
          Holidays
        </h2><p class="mt-2 text-sm text-muted">
          View the organization holiday calendar synchronized from ERP.
        </p>
      </div>
    </div>
    <ListControls
      v-model:search="list.search.value"
      :active="list.active.value"
      search-placeholder="Search holiday calendars"
      @clear="list.clear"
    />
    <UAlert
      v-if="error"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-sun-medium"
      title="Your holiday calendar is taking a short break"
      description="We couldn’t refresh the holiday list right now. Please try again in a moment."
      :actions="[{ label: 'Refresh calendar', onClick: () => refresh() }]"
    /><div
      v-else
      class="mt-7 grid gap-5 lg:grid-cols-[20rem_1fr]"
    >
      <aside class="people-card h-fit overflow-hidden">
        <div class="border-b border-[var(--people-border)] p-4">
          <h3 class="font-semibold">
            Calendars
          </h3>
        </div><div
          v-if="pending"
          class="space-y-3 p-4"
        >
          <USkeleton
            v-for="i in 3"
            :key="i"
            class="h-16"
          />
        </div><button
          v-for="item in data?.lists"
          v-else
          :key="item.id"
          class="flex w-full items-center gap-3 border-b border-[var(--people-border)] p-4 text-left last:border-0"
          :class="selectedId === item.id ? 'bg-primary-50 dark:bg-primary-950/20' : 'hover:bg-muted/5'"
          @click="selectedId = item.id"
        >
          <span class="grid size-10 place-items-center rounded-xl bg-[var(--people-lavender)]"><UIcon name="i-lucide-calendar-days" /></span><span class="min-w-0 flex-1"><span class="block truncate font-medium">{{ item.name }}</span><span class="mt-1 block text-xs text-muted">{{ item.weekly_off_day }} weekly off</span></span><UBadge
            v-if="item.is_default"
            color="primary"
            variant="soft"
            size="sm"
          >
            Default
          </UBadge>
        </button>
      </aside><section class="people-card overflow-hidden">
        <div class="flex flex-col gap-3 border-b border-[var(--people-border)] p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <h3 class="font-semibold">
              {{ selected?.name || 'Select a calendar' }}
            </h3><p
              v-if="selected"
              class="mt-1 text-sm text-muted"
            >
              {{ selected.from_date }} – {{ selected.to_date }}
            </p>
          </div>
        </div><div
          v-if="selected && !selected.holidays.length"
          class="p-12 text-center text-sm text-muted"
        >
          No holidays in this calendar.
        </div><div
          v-else
          class="divide-y divide-[var(--people-border)]"
        >
          <article
            v-for="item in selected?.holidays"
            :key="item.id"
            class="flex items-center gap-4 p-4 sm:px-6"
          >
            <div class="w-20 shrink-0 text-sm font-semibold">
              {{ formatDate(item.holiday_date) }}
            </div><span
              class="grid size-10 shrink-0 place-items-center rounded-xl"
              :class="item.is_weekly_off ? 'bg-muted/10' : 'bg-[var(--people-peach)]'"
            ><UIcon :name="item.is_weekly_off ? 'i-lucide-calendar-off' : 'i-lucide-party-popper'" /></span><div class="min-w-0 flex-1">
              <p class="font-medium">
                {{ item.name }}
              </p><p class="mt-1 truncate text-xs text-muted">
                {{ item.description || (item.is_weekly_off ? 'Weekly off' : 'Organization holiday') }}
              </p>
            </div>
          </article>
        </div>
      </section>
    </div>
    <ListPagination
      v-if="data"
      v-model:page="list.page.value"
      v-model:page-size="list.pageSize.value"
      :total="data.total"
      :loading="pending"
      label="calendars"
    />
  </div>
</template>
