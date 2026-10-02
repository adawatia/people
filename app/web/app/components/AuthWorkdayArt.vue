<script setup lang="ts">
const props = defineProps<{ technical: boolean }>()
const markers = computed(() => props.technical
  ? [
      { label: 'Access', icon: 'i-lucide-shield-check' },
      { label: 'Audit', icon: 'i-lucide-scroll-text' },
      { label: 'System', icon: 'i-lucide-settings' }
    ]
  : [
      { label: 'Attendance', icon: 'i-lucide-clock' },
      { label: 'Time off', icon: 'i-lucide-calendar-days' },
      { label: 'Schedules', icon: 'i-lucide-calendar-clock' }
    ])
</script>

<template>
  <div
    class="auth-art"
    aria-hidden="true"
  >
    <div
      v-for="marker in markers"
      :key="marker.label"
      class="auth-flow-node"
    >
      <span class="auth-flow-icon"><UIcon
        :name="marker.icon"
        class="size-5"
      /></span>
      <span>{{ marker.label }}</span>
    </div>
  </div>
</template>
