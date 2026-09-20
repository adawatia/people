<script setup lang="ts">
defineProps<{ compact?: boolean }>()
</script>

<template>
  <div class="flex items-center gap-3">
    <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-primary text-white shadow-sm shadow-primary/20">
      <UIcon
        name="i-lucide-users-round"
        class="size-5"
      />
    </span>
    <span
      v-if="!compact"
      class="leading-none"
    >
      <span class="block text-[17px] font-semibold tracking-tight">People</span>
      <span class="mt-1 block text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">by Datlabs</span>
    </span>
  </div>
</template>
