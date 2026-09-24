<script setup lang="ts">
defineProps<{ compact?: boolean }>()
</script>

<template>
  <div class="flex items-center gap-3">
    <picture class="block size-9 shrink-0 overflow-hidden rounded-xl shadow-sm shadow-primary/20">
      <source
        media="(prefers-color-scheme: dark)"
        srcset="/branding/people-app-icon-dark.svg"
      >
      <img
        src="/branding/people-app-icon-light.svg"
        alt="People"
        class="size-full object-cover"
      >
    </picture>
    <span
      v-if="!compact"
      class="leading-none"
    >
      <span class="block text-[17px] font-semibold tracking-tight">People</span>
      <span class="mt-1 block text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">by Datlabs</span>
    </span>
  </div>
</template>
