<script setup lang="ts">
defineProps<{ active?: boolean, sorts?: { label: string, value: string }[] }>()
const search = defineModel<string>('search', { default: '' })
const sortBy = defineModel<string>('sortBy', { default: '' })
const sortOrder = defineModel<string>('sortOrder', { default: 'desc' })
defineEmits<{ clear: [] }>()
</script>

<template>
  <div class="my-4 flex flex-wrap items-end gap-3">
    <UFormField
      label="Search"
      class="min-w-48 flex-1"
    >
      <UInput
        v-model="search"
        icon="i-lucide-search"
        placeholder="Search records"
        class="w-full"
      />
    </UFormField>
    <slot />
    <UFormField
      v-if="sorts?.length"
      label="Sort by"
    >
      <USelect
        v-model="sortBy"
        :items="sorts"
        aria-label="Sort by"
      />
    </UFormField>
    <UFormField
      v-if="sorts?.length"
      label="Order"
    >
      <USelect
        v-model="sortOrder"
        :items="[{ label: 'Newest / descending', value: 'desc' }, { label: 'Oldest / ascending', value: 'asc' }]"
      />
    </UFormField>
    <UButton
      v-if="active"
      icon="i-lucide-filter-x"
      variant="outline"
      color="neutral"
      class="min-h-11"
      @click="$emit('clear')"
    >
      Clear filters
    </UButton>
  </div>
</template>
