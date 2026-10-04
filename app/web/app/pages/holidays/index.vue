<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { Holiday, HolidayList } from '#shared/types/workforce'

useSeoMeta({ title: 'Holidays' })
const api = useHrmsApi()
const list = useListState({ sort_order: 'asc' })
const selectedId = ref<number>()
const unit = list.field('unit_id')
// RemoteSelect models a number; 0 means "All units".
const unitSelection = computed({
  get: () => Number(unit.value) || 0,
  set: (value: number) => { unit.value = value > 0 ? String(value) : '' }
})
const sortOptions = [
  { label: 'Name', value: 'name' },
  { label: 'Newest', value: 'id' }
]
// Holiday calendars are ERP-owned; the UI is display-only.
const { data: rawData, pending, error, refresh } = await useAsyncData('holiday-workspace', async () => {
  const lists = await api.request<PaginatedResponse<HolidayList>>('holidays/lists', {
    query: { ...list.query.value, unit_id: unitSelection.value || undefined }
  })
  return { lists: lists.items, ...lists }
}, { watch: [list.query, unitSelection] })
const data = useRetainedData(rawData)
watchEffect(() => {
  if (!data.value?.lists.some(item => item.id === selectedId.value) && data.value?.lists[0]) selectedId.value = data.value.lists[0].id
})
const selected = computed(() => data.value?.lists.find(item => item.id === selectedId.value))
const calendarOptions = computed(() => (data.value?.lists || []).map(item => ({ label: item.name, value: item.id })))

const dateFormat = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
const weekdayFormat = new Intl.DateTimeFormat('en-IN', { weekday: 'long' })
const monthFormat = new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric' })
const shortDateFormat = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' })
const formatDate = (value: string) => dateFormat.format(new Date(`${value}T00:00:00`))
const formatWeekday = (value: string) => weekdayFormat.format(new Date(`${value}T00:00:00`))
const formatMonth = (value: string) => monthFormat.format(new Date(`${value}T00:00:00`))
const formatShort = (value: string) => shortDateFormat.format(new Date(`${value}T00:00:00`))
const weeklyOffLabel = (value: string) => value.charAt(0) + value.slice(1).toLowerCase().replace(/_/g, ' ')

const holidays = computed(() => [...(selected.value?.holidays || [])].sort((a, b) => a.holiday_date.localeCompare(b.holiday_date)))
const holidayCount = computed(() => holidays.value.filter(item => !item.is_weekly_off).length)
const weeklyOffCount = computed(() => holidays.value.filter(item => item.is_weekly_off).length)
const today = new Date().toISOString().slice(0, 10)
const nextHoliday = computed(() => holidays.value.find(item => !item.is_weekly_off && item.holiday_date > today))

const monthGroups = computed(() => {
  const groups: { key: string, label: string, items: Holiday[] }[] = []
  for (const item of holidays.value) {
    const key = item.holiday_date.slice(0, 7)
    const current = groups[groups.length - 1]
    if (current && current.key === key) current.items.push(item)
    else groups.push({ key, label: formatMonth(item.holiday_date), items: [item] })
  }
  return groups
})

const summaryItems = computed(() => [
  { label: 'Holidays', value: holidayCount.value, icon: 'i-lucide-party-popper', note: 'Declared in this calendar' },
  { label: 'Weekly offs', value: weeklyOffCount.value, icon: 'i-lucide-calendar-off', note: 'Generated from the weekly off day' },
  { label: 'Next holiday', value: nextHoliday.value ? formatShort(nextHoliday.value.holiday_date) : '—', icon: 'i-lucide-calendar-heart', note: nextHoliday.value?.name }
])
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
        <h1 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Holidays
        </h1>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-muted">
          View the organization holiday calendar synchronized from ERP. Calendars and weekly offs are maintained in ERP and shown here for reference.
        </p>
      </div>
    </div>

    <ListControls
      v-model:search="list.search.value"
      v-model:sort-by="list.sortBy.value"
      v-model:sort-order="list.sortOrder.value"
      :sorts="sortOptions"
      :active="list.active.value"
      search-placeholder="Search holiday calendars"
      @clear="list.clear"
    >
      <UFormField
        label="Unit"
        class="min-w-0"
      >
        <RemoteSelect
          v-model="unitSelection"
          endpoint="org/units"
          label="All units"
          clearable
        />
      </UFormField>
    </ListControls>

    <UAlert
      v-if="error"
      class="mt-6"
      color="warning"
      variant="soft"
      icon="i-lucide-sun-medium"
      title="Holiday calendars could not be loaded"
      description="We couldn’t refresh the holiday calendars right now. Please try again in a moment."
      :actions="[{ label: 'Refresh calendars', onClick: () => refresh() }]"
    />

    <ListEmptyState
      v-if="!pending && !error && !data?.lists.length"
      title="No holiday calendars found"
      description="Holiday calendars are synchronized from ERP."
      :filtered="list.active.value"
      @reset="list.clear"
    />

    <div
      v-if="pending || data?.lists.length"
      class="mt-7"
    >
      <div class="lg:hidden">
        <div
          v-if="pending && !data"
          class="people-card p-4"
        >
          <USkeleton class="h-11 w-full" />
        </div>
        <UFormField
          v-else
          label="Calendar"
        >
          <USelect
            v-model="selectedId"
            :items="calendarOptions"
            class="w-full"
          />
        </UFormField>
      </div>

      <div class="mt-5 grid gap-6 lg:mt-0 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <aside class="people-card hidden h-fit overflow-hidden lg:block">
          <div class="border-b border-[var(--people-border)] p-4">
            <h2 class="font-semibold">
              Calendars
            </h2>
          </div>
          <div
            v-if="pending && !data"
            class="space-y-3 p-4"
          >
            <USkeleton
              v-for="i in 3"
              :key="i"
              class="h-16"
            />
          </div>
          <button
            v-for="item in data?.lists"
            v-else
            :key="item.id"
            type="button"
            class="flex min-h-11 w-full items-center gap-3 border-b border-[var(--people-border)] p-4 text-left last:border-0"
            :class="selectedId === item.id ? 'bg-[var(--people-forest)]' : 'hover:bg-muted/5'"
            :aria-pressed="selectedId === item.id"
            @click="selectedId = item.id"
          >
            <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-[var(--people-forest)] text-[var(--people-forest-ink)]"><UIcon name="i-lucide-calendar-days" /></span>
            <span class="min-w-0 flex-1"><span class="block break-words font-medium">{{ item.name }}</span><span class="mt-1 block text-xs text-muted">{{ weeklyOffLabel(item.weekly_off_day) }} weekly off · {{ item.holidays.length }} day{{ item.holidays.length === 1 ? '' : 's' }}</span></span>
            <UBadge
              v-if="item.is_default"
              color="primary"
              variant="soft"
              size="sm"
            >
              Default
            </UBadge>
          </button>
        </aside>

        <section class="min-w-0 space-y-6">
          <DashboardSummary
            v-if="data || pending"
            label="Selected calendar summary"
            variant="compact"
            :pending="pending && !data"
            :unavailable="!selected"
            :items="summaryItems"
          />

          <div class="people-card min-w-0 overflow-hidden">
            <div class="flex flex-col gap-3 border-b border-[var(--people-border)] p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
              <div class="min-w-0">
                <h2 class="font-semibold">
                  {{ selected?.name || 'Select a calendar' }}
                </h2>
                <p
                  v-if="selected"
                  class="mt-1 text-sm text-muted"
                >
                  {{ selected.from_date }} – {{ selected.to_date }}
                </p>
              </div>
              <div
                v-if="selected"
                class="flex flex-wrap items-center gap-2"
              >
                <UBadge
                  color="neutral"
                  variant="soft"
                  icon="i-lucide-calendar-off"
                  :label="`${weeklyOffLabel(selected.weekly_off_day)} weekly off`"
                />
                <UBadge
                  v-if="selected.is_default"
                  color="primary"
                  variant="soft"
                  label="Default"
                />
              </div>
            </div>

            <div
              v-if="pending && !data"
              class="space-y-3 p-5"
            >
              <USkeleton
                v-for="i in 6"
                :key="i"
                class="h-12 w-full"
              />
            </div>

            <div
              v-else-if="selected && !holidays.length"
              class="px-6 py-12 text-center text-sm text-muted"
            >
              No holidays in this calendar.
            </div>

            <template v-else-if="selected">
              <div
                class="hidden overflow-x-auto md:block"
                tabindex="0"
                aria-label="Holiday table"
              >
                <table class="w-full min-w-[640px] text-left text-sm">
                  <thead class="bg-muted/5 text-xs uppercase tracking-wide text-muted">
                    <tr>
                      <th class="px-6 py-3 font-semibold">
                        Date
                      </th>
                      <th class="px-4 py-3 font-semibold">
                        Day
                      </th>
                      <th class="px-4 py-3 font-semibold">
                        Holiday
                      </th>
                      <th class="px-4 py-3 font-semibold">
                        Type
                      </th>
                      <th class="px-6 py-3 font-semibold">
                        Description
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <template
                      v-for="group in monthGroups"
                      :key="group.key"
                    >
                      <tr class="bg-[var(--people-forest)]/40">
                        <td
                          colspan="5"
                          class="px-6 py-2 text-xs font-semibold uppercase tracking-wide text-muted"
                        >
                          {{ group.label }} · {{ group.items.length }} day{{ group.items.length === 1 ? '' : 's' }}
                        </td>
                      </tr>
                      <tr
                        v-for="item in group.items"
                        :key="item.id"
                        class="h-[52px] border-t border-[var(--people-border)]"
                      >
                        <td class="px-6 py-3 font-semibold tabular-nums">
                          {{ formatDate(item.holiday_date) }}
                        </td>
                        <td class="px-4 py-3 text-muted">
                          {{ formatWeekday(item.holiday_date) }}
                        </td>
                        <td class="px-4 py-3 font-medium">
                          {{ item.name }}
                        </td>
                        <td class="px-4 py-3">
                          <UBadge
                            :color="item.is_weekly_off ? 'neutral' : 'info'"
                            variant="soft"
                            :label="item.is_weekly_off ? 'Weekly off' : 'Holiday'"
                          />
                        </td>
                        <td class="max-w-72 break-words px-6 py-3 text-muted">
                          {{ item.description || '—' }}
                        </td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>

              <div class="divide-y divide-[var(--people-border)] md:hidden">
                <template
                  v-for="group in monthGroups"
                  :key="group.key"
                >
                  <p class="bg-[var(--people-forest)]/40 px-5 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
                    {{ group.label }}
                  </p>
                  <article
                    v-for="item in group.items"
                    :key="item.id"
                    class="flex min-h-[60px] items-start gap-4 p-5"
                  >
                    <span
                      class="grid size-10 shrink-0 place-items-center rounded-xl"
                      :style="item.is_weekly_off ? { background: 'var(--people-blue)', color: 'var(--people-blue-ink)' } : { background: 'var(--people-peach)', color: 'var(--people-peach-ink)' }"
                    >
                      <UIcon :name="item.is_weekly_off ? 'i-lucide-calendar-off' : 'i-lucide-party-popper'" />
                    </span>
                    <div class="min-w-0 flex-1">
                      <div class="flex flex-wrap items-center gap-2">
                        <p class="font-medium">
                          {{ item.name }}
                        </p>
                        <UBadge
                          :color="item.is_weekly_off ? 'neutral' : 'info'"
                          variant="soft"
                          :label="item.is_weekly_off ? 'Weekly off' : 'Holiday'"
                        />
                      </div>
                      <p class="mt-1 text-xs text-muted">
                        {{ formatDate(item.holiday_date) }} · {{ formatWeekday(item.holiday_date) }}
                      </p>
                      <p
                        v-if="item.description"
                        class="mt-2 break-words text-sm leading-6 text-muted"
                      >
                        {{ item.description }}
                      </p>
                    </div>
                  </article>
                </template>
              </div>
            </template>
          </div>
        </section>
      </div>
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
