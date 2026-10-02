<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

import type { HrmsNotification } from '#shared/types/notification'

useSeoMeta({ title: 'Notifications' })
const api = useHrmsApi()
const toast = useToast()
const list = useListState({ filter: 'all' })
const filter = list.field('filter')
const markingAll = ref(false)
const workingId = ref<number | null>(null)
const { data: rawNotifications, pending, error, refresh } = await useAsyncData('notifications', (_app, { signal }) => api.request<PaginatedResponse<HrmsNotification>>('notifications', { signal, query: { ...list.query.value, unread: filter.value === 'unread' ? true : undefined } }), { watch: [list.query, filter] })
const notifications = useRetainedData(rawNotifications)
const { data: rawCounts, refresh: refreshCounts } = await useAsyncData('notification-count', () => api.request<{ unread_count: number }>('notifications/unread-count'))
const counts = useRetainedData(rawCounts)
const visible = computed(() => notifications.value?.items || [])
const unread = computed(() => counts.value?.unread_count || 0)
const iconFor = (type: string) => type.includes('leave') ? 'i-lucide-calendar-days' : type.includes('attendance') ? 'i-lucide-calendar-check-2' : type.includes('overtime') ? 'i-lucide-timer' : 'i-lucide-bell'
const timeAgo = (value: string) => new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 3600000)), 'hour')
async function openNotification(item: HrmsNotification) {
  if (markingAll.value || workingId.value !== null) return
  workingId.value = item.notification_id
  try {
    if (!item.is_read) {
      await api.request(`notifications/${item.notification_id}/read`, { method: 'PATCH' })
      await Promise.all([refresh(), refreshCounts()])
    }
    // Notification links are application paths, never arbitrary external URLs.
    if (item.link?.startsWith('/') && !item.link.startsWith('//')) await navigateTo(item.link)
  } catch {
    toast.add({ title: 'Could not update notification', description: 'Please try again.', color: 'error' })
  } finally {
    workingId.value = null
  }
}
async function markAll() {
  if (markingAll.value || workingId.value !== null) return
  markingAll.value = true
  try {
    await api.request('notifications/mark-all-read', { method: 'POST' })
    await Promise.all([refresh(), refreshCounts()])
    toast.add({ title: 'All caught up', color: 'success', icon: 'i-lucide-check-check' })
  } catch {
    toast.add({ title: 'Could not mark notifications read', description: 'Please try again.', color: 'error' })
  } finally {
    markingAll.value = false
  }
}
</script>

<template>
  <div class="people-page mx-auto max-w-4xl">
    <DataFeedback
      :pending="pending"
      :error="error"
      :has-data="Boolean(notifications)"
    />
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Notifications
        </h1><p class="mt-2 text-sm text-muted">
          Approvals, attendance alerts, and account updates in one place.
        </p>
      </div><UButton
        v-if="unread"
        color="neutral"
        variant="soft"
        icon="i-lucide-check-check"
        :loading="markingAll"
        :disabled="markingAll || workingId !== null"
        @click="markAll"
      >
        Mark all read
      </UButton>
    </div>
    <ListControls
      v-model:search="list.search.value"
      :active="list.active.value"
      search-placeholder="Search notification titles"
      @clear="list.clear"
    />
    <div class="mt-7 flex gap-1 rounded-xl bg-muted/5 p-1 sm:w-fit">
      <button
        v-for="option in [{ key: 'all', label: 'All' }, { key: 'unread', label: `Unread (${unread})` }]"
        :key="option.key"
        class="rounded-lg px-4 py-2 text-sm font-medium"
        :class="filter === option.key ? 'bg-[var(--people-surface)] shadow-sm' : 'text-muted'"
        :aria-pressed="filter === option.key"
        @click="filter = option.key as 'all' | 'unread'"
      >
        {{ option.label }}
      </button>
    </div>
    <UAlert
      v-if="error"
      class="mt-5"
      color="warning"
      variant="soft"
      icon="i-lucide-bell-off"
      title="Updates could not be loaded"
      description="We couldn’t check for new updates right now. Please try again in a moment."
      :actions="[{ label: 'Refresh notifications', onClick: () => refresh() }]"
    />
    <section
      v-else
      class="people-card mt-5 overflow-hidden"
    >
      <div
        v-if="pending && !notifications"
        class="space-y-3 p-5"
      >
        <USkeleton
          v-for="i in 5"
          :key="i"
          class="h-20 w-full"
        />
      </div>
      <ListEmptyState
        v-else-if="!error && !visible.length"
        :title="list.active.value ? 'No matching notifications' : 'You’re all caught up'"
        description="New notifications will appear here when they are available."
        :filtered="list.active.value"
        icon="i-lucide-bell"
        @reset="list.clear"
      />
      <div
        v-else-if="visible.length"
        class="divide-y divide-[var(--people-border)]"
      >
        <button
          v-for="item in visible"
          :key="item.notification_id"
          type="button"
          class="flex w-full gap-4 p-5 text-left transition-colors hover:bg-muted/5 sm:px-6"
          :class="!item.is_read && 'bg-[var(--people-lavender)]'"
          :disabled="markingAll || workingId !== null"
          @click="openNotification(item)"
        >
          <span class="grid size-11 shrink-0 place-items-center rounded-xl bg-[var(--people-lavender)]"><UIcon
            :name="iconFor(item.notification_type)"
            class="size-5"
          /></span><span class="min-w-0 flex-1"><span class="flex items-start justify-between gap-3"><span class="font-semibold">{{ item.title }}</span><span class="shrink-0 text-xs text-muted">{{ timeAgo(item.created_at) }}</span></span><span class="mt-1 block text-sm leading-6 text-muted">{{ item.message }}</span></span><span
            v-if="!item.is_read"
            class="mt-2 size-2 shrink-0 rounded-full bg-primary"
          />
        </button>
      </div>
    </section>
    <ListPagination
      v-if="notifications"
      v-model:page="list.page.value"
      v-model:page-size="list.pageSize.value"
      :total="notifications?.total || 0"
      :total-pages="notifications?.total_pages"
      :loading="pending"
    />
  </div>
</template>
