<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
import type { HrmsNotification } from '#shared/types/notification'

useSeoMeta({ title: 'Notifications' })
const api = useHrmsApi()
const toast = useToast()
const filter = ref<'all' | 'unread'>('all')
const workingId = ref<number | null>(null)
const { data: notifications, pending, error, refresh } = await useAsyncData('notifications', () => api.request<HrmsNotification[]>('notifications'))
const visible = computed(() => (notifications.value || []).filter(item => filter.value === 'all' || !item.is_read))
const unread = computed(() => (notifications.value || []).filter(item => !item.is_read).length)
const iconFor = (type: string) => type.includes('leave') ? 'i-lucide-calendar-days' : type.includes('attendance') ? 'i-lucide-calendar-check-2' : type.includes('overtime') ? 'i-lucide-timer' : 'i-lucide-bell'
const timeAgo = (value: string) => new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 3600000)), 'hour')
async function openNotification(item: HrmsNotification) {
  if (!item.is_read) {
    workingId.value = item.notification_id
    await api.request(`notifications/${item.notification_id}/read`, { method: 'PATCH' })
    item.is_read = true
    workingId.value = null
  }
  if (item.link) await navigateTo(item.link)
}
async function markAll() {
  await api.request('notifications/mark-all-read', { method: 'POST' })
  for (const item of notifications.value || []) item.is_read = true
  toast.add({ title: 'All caught up', color: 'success', icon: 'i-lucide-check-check' })
}
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Updates
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Notifications
        </h2><p class="mt-2 text-sm text-muted">
          Approvals, attendance alerts, and account updates in one place.
        </p>
      </div><UButton
        v-if="unread"
        color="neutral"
        variant="soft"
        icon="i-lucide-check-check"
        @click="markAll"
      >
        Mark all read
      </UButton>
    </div>
    <div class="mt-7 flex gap-1 rounded-xl bg-muted/5 p-1 sm:w-fit">
      <button
        v-for="option in [{ key: 'all', label: 'All' }, { key: 'unread', label: `Unread (${unread})` }]"
        :key="option.key"
        class="rounded-lg px-4 py-2 text-sm font-medium"
        :class="filter === option.key ? 'bg-[var(--people-surface)] shadow-sm' : 'text-muted'"
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
      title="Your notifications are taking a short break"
      description="We couldn’t check for new updates right now. Please try again in a moment."
      :actions="[{ label: 'Refresh notifications', onClick: () => refresh() }]"
    />
    <section
      v-else
      class="people-card mt-5 overflow-hidden"
    >
      <div
        v-if="pending"
        class="space-y-3 p-5"
      >
        <USkeleton
          v-for="i in 5"
          :key="i"
          class="h-20 w-full"
        />
      </div>
      <div
        v-else-if="!visible.length"
        class="p-12 text-center"
      >
        <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-[var(--people-lavender)]"><UIcon
          name="i-lucide-bell-ring"
          class="size-6"
        /></span><h3 class="mt-4 font-semibold">
          You're all caught up
        </h3><p class="mt-1 text-sm text-muted">
          New updates will appear here.
        </p>
      </div>
      <div
        v-else
        class="divide-y divide-[var(--people-border)]"
      >
        <button
          v-for="item in visible"
          :key="item.notification_id"
          type="button"
          class="flex w-full gap-4 p-5 text-left transition-colors hover:bg-muted/5 sm:px-6"
          :class="!item.is_read && 'bg-primary-50/40 dark:bg-primary-950/10'"
          :disabled="workingId === item.notification_id"
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
  </div>
</template>
