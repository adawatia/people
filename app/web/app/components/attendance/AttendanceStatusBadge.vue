<script setup lang="ts">
const props = defineProps<{ status: string }>()

const config = computed(() => {
  const values: Record<string, { label: string, icon: string, class: string }> = {
    PRESENT: { label: 'Present', icon: 'i-lucide-circle-check', class: 'bg-[var(--people-mint)] text-emerald-800 dark:text-emerald-200' },
    ABSENT: { label: 'Absent', icon: 'i-lucide-circle-x', class: 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-200' },
    HALF_DAY: { label: 'Half day', icon: 'i-lucide-circle-dot-dashed', class: 'bg-[var(--people-peach)] text-amber-800 dark:text-amber-200' },
    ON_LEAVE: { label: 'On leave', icon: 'i-lucide-calendar-heart', class: 'bg-[var(--people-forest)] text-[var(--people-forest-ink)]' },
    HOLIDAY: { label: 'Holiday', icon: 'i-lucide-party-popper', class: 'bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-200' },
    WEEKLY_OFF: { label: 'Weekly off', icon: 'i-lucide-coffee', class: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200' },
    MISSED_PUNCH: { label: 'Missed punch', icon: 'i-lucide-triangle-alert', class: 'bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-200' },
    WORK_FROM_HOME: { label: 'Remote', icon: 'i-lucide-house-wifi', class: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-950/60 dark:text-cyan-200' }
  }
  return values[props.status] || { label: props.status.replaceAll('_', ' '), icon: 'i-lucide-circle', class: 'bg-muted/10 text-muted' }
})
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
    :class="config.class"
  >
    <UIcon
      :name="config.icon"
      class="size-3.5"
    />
    {{ config.label }}
  </span>
</template>
