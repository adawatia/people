<script setup lang="ts">
defineProps<{ pending?: boolean, error?: unknown, hasData?: boolean }>()
</script>

<template>
  <p
    v-if="pending || (error && hasData)"
    class="people-data-feedback"
    role="status"
    aria-live="polite"
  >
    {{ pending ? hasData ? 'Updating results… Previous results remain visible.' : 'Loading results…' : 'Showing results from the last successful update. Retry to get the latest information.' }}
  </p>
</template>
