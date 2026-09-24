<script setup lang="ts">
const props = defineProps<{ total: number, totalPages?: number, loading?: boolean, label?: string }>()
const page = defineModel<number>('page', { required: true })
const pageSize = defineModel<number>('pageSize', { required: true })
const pages = computed(() => props.totalPages ?? Math.max(1, Math.ceil(props.total / pageSize.value)))
const start = computed(() => props.total ? (page.value - 1) * pageSize.value + 1 : 0)
const end = computed(() => Math.min(page.value * pageSize.value, props.total))
watch([() => props.total, () => props.loading], () => {
  if (!props.loading && page.value > pages.value) page.value = pages.value
})
</script>

<template>
  <nav
    aria-label="Results pagination"
    class="my-4 flex flex-wrap items-center justify-between gap-4 border-t border-default pt-4"
  >
    <p
      class="text-sm text-muted"
      aria-live="polite"
    >
      Showing {{ start }}–{{ end }} of {{ total }} {{ label || 'results' }}
    </p>
    <div class="hidden sm:block">
      <UPagination
        v-model:page="page"
        :total="total"
        :items-per-page="pageSize"
        :disabled="loading"
        :sibling-count="1"
      />
    </div>
    <div class="flex w-full items-center justify-between gap-2 sm:hidden">
      <UButton
        variant="outline"
        color="neutral"
        class="min-h-11"
        :disabled="loading || page <= 1"
        @click="page--"
      >
        Previous
      </UButton>
      <span class="text-sm">Page {{ page }} of {{ pages }}</span>
      <UButton
        variant="outline"
        color="neutral"
        class="min-h-11"
        :disabled="loading || page >= pages"
        @click="page++"
      >
        Next
      </UButton>
    </div>
    <UFormField
      label="Rows per page"
      orientation="horizontal"
    >
      <USelect
        v-model="pageSize"
        :items="[10, 25, 50, 100]"
        :disabled="loading"
        aria-label="Rows per page"
      />
    </UFormField>
  </nav>
</template>
