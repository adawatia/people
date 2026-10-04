<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  description?: string
  filtered?: boolean
  icon?: string
}>(), { description: 'Records will appear here when they are available.', filtered: false, icon: 'i-lucide-inbox' })
const emit = defineEmits<{ reset: [] }>()
const root = useTemplateRef('root')
async function reset() {
  const search = root.value?.closest('.people-page')?.querySelector<HTMLInputElement>('input[type=search]')
  emit('reset')
  await nextTick()
  search?.focus()
}
</script>

<template>
  <div
    ref="root"
    class="px-5 py-10 text-center"
    role="status"
  >
    <UIcon
      :name="filtered ? 'i-lucide-filter-x' : icon"
      class="size-8 text-primary"
    />
    <h3 class="mt-3 font-semibold">
      {{ title }}
    </h3>
    <p class="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">
      {{ filtered ? 'Try changing your search or resetting filters to see more results.' : description }}
    </p>
    <UButton
      v-if="filtered"
      class="mt-4"
      color="neutral"
      variant="outline"
      icon="i-lucide-rotate-ccw"
      @click="reset"
    >
      Reset filters
    </UButton>
  </div>
</template>
