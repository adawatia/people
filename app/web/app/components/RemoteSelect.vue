<script setup lang="ts">
import type { PaginatedResponse } from '#shared/types/pagination'

const props = defineProps<{ endpoint: string, label: string, filters?: Record<string, unknown> }>()
const model = defineModel<number>({ default: 0 })
const api = useHrmsApi()
const search = ref('')
const debounced = ref('')
const page = ref(1)
let timer: ReturnType<typeof setTimeout> | undefined
watch(search, (value) => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    debounced.value = value.trim()
  }, 300)
})
onBeforeUnmount(() => clearTimeout(timer))
watch(() => props.filters, () => {
  page.value = 1
}, { deep: true })
const { data, pending, error, refresh } = useLazyAsyncData(`lookup-${useId()}`, (_app, { signal }) => api.request<PaginatedResponse<{ id: number, name: string }>>(props.endpoint, { signal, query: { ...props.filters, page: page.value, page_size: 25, search: debounced.value || undefined } }), { watch: [page, debounced, () => props.filters] })
const selected = ref<{ id: number, name: string }>()
watch([model, data], () => {
  const item = data.value?.items.find(item => item.id === model.value)
  if (item) selected.value = item
})
const items = computed(() => [{ id: 0, name: props.label }, ...(selected.value && !data.value?.items.some(item => item.id === selected.value?.id) ? [selected.value] : []), ...(data.value?.items || [])])
</script>

<template>
  <USelectMenu
    v-model="model"
    v-model:search-term="search"
    :items="items"
    value-key="id"
    label-key="name"
    :ignore-filter="true"
    :loading="pending"
    :aria-label="label"
    class="min-w-44"
  >
    <template #content-bottom>
      <UAlert
        v-if="error"
        title="Could not load options"
        color="error"
        :actions="[{ label: 'Retry', onClick: () => refresh() }]"
      />
      <div class="flex items-center justify-between gap-2 border-t border-default p-2">
        <UButton
          aria-label="Previous options"
          icon="i-lucide-chevron-left"
          variant="ghost"
          :disabled="pending || page <= 1"
          @click.stop="page--"
        />
        <span class="text-xs">{{ page }} / {{ data?.total_pages || 1 }} · {{ data?.total || 0 }} results</span>
        <UButton
          aria-label="Next options"
          icon="i-lucide-chevron-right"
          variant="ghost"
          :disabled="pending || !data?.has_next"
          @click.stop="page++"
        />
      </div>
    </template>
  </USelectMenu>
</template>
