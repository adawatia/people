<script setup lang="ts">
const pwa = usePWA()
const dismissed = ref(false)

function reload() {
  if (pwa?.updateServiceWorker) {
    pwa.updateServiceWorker()
  }
}

function dismiss() {
  dismissed.value = true
}
</script>

<template>
  <div
    v-if="pwa?.needRefresh && !dismissed"
    class="fixed bottom-4 right-4 z-50 max-w-sm shadow-lg"
    role="alert"
    aria-live="polite"
  >
    <UAlert
      color="primary"
      variant="subtle"
      icon="i-lucide-sparkles"
      title="Update available"
      description="A new version of Emploi is ready. Reload to apply updates."
      :actions="[
        { label: 'Reload', color: 'primary', variant: 'solid', size: 'xs', onClick: reload },
        { label: 'Later', color: 'neutral', variant: 'ghost', size: 'xs', onClick: dismiss }
      ]"
    />
  </div>
</template>
