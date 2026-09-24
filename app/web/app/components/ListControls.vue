<script setup lang="ts">
const props = withDefaults(defineProps<{
  active?: boolean
  sorts?: { label: string, value: string }[]
  searchPlaceholder?: string
  label?: string
}>(), {
  active: false,
  sorts: () => [],
  searchPlaceholder: 'Search records',
  label: 'Filter results'
})
const search = defineModel<string>('search', { default: '' })
const sortBy = defineModel<string>('sortBy', { default: '' })
const sortOrder = defineModel<string>('sortOrder', { default: 'desc' })
const emit = defineEmits<{ clear: [] }>()
const slots = useSlots()
const expanded = ref(false)
const hasAdvanced = computed(() => Boolean(props.sorts.length || slots.default))

watch(() => props.active, (active) => {
  if (active && hasAdvanced.value) expanded.value = true
})

function clear() {
  emit('clear')
  expanded.value = false
}
</script>

<template>
  <section
    class="people-card my-5 overflow-hidden"
    aria-label="List filters"
  >
    <div class="flex items-center justify-between gap-3 border-b border-[var(--people-border)] px-4 py-3 sm:px-5">
      <div class="flex min-w-0 items-center gap-2">
        <span class="grid size-8 shrink-0 place-items-center rounded-lg bg-[var(--people-blue)] text-primary">
          <UIcon
            name="i-lucide-list-filter"
            class="size-4"
          />
        </span>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold">
            {{ label }}
          </p>
          <p class="hidden text-xs text-muted sm:block">
            Search, narrow, and order this list
          </p>
        </div>
        <UBadge
          v-if="active"
          color="primary"
          variant="soft"
          size="sm"
        >
          Active
        </UBadge>
      </div>
      <UButton
        v-if="active"
        icon="i-lucide-rotate-ccw"
        variant="ghost"
        color="neutral"
        size="sm"
        @click="clear"
      >
        Reset
      </UButton>
    </div>

    <div class="p-4 sm:p-5">
      <div class="flex items-center gap-2">
        <UFormField
          label="Search"
          class="min-w-0 flex-1"
        >
          <UInput
            v-model="search"
            icon="i-lucide-search"
            :placeholder="searchPlaceholder"
            autocomplete="off"
            class="w-full"
          />
        </UFormField>
        <UButton
          v-if="hasAdvanced"
          class="mt-6 min-h-10 md:hidden"
          color="neutral"
          variant="outline"
          :icon="expanded ? 'i-lucide-chevron-up' : 'i-lucide-sliders-horizontal'"
          :aria-expanded="expanded"
          aria-controls="mobile-list-filters"
          @click="expanded = !expanded"
        >
          {{ expanded ? 'Hide' : 'Filters' }}
        </UButton>
      </div>

      <div
        v-if="hasAdvanced"
        id="mobile-list-filters"
        class="mt-4 gap-3 border-t border-[var(--people-border)] pt-4 md:mt-3 md:grid md:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))] md:border-0 md:pt-0"
        :class="expanded ? 'grid' : 'hidden'"
      >
        <slot />
        <UFormField
          v-if="sorts.length"
          label="Sort by"
        >
          <USelect
            v-model="sortBy"
            :items="sorts"
            placeholder="Default order"
            aria-label="Sort by"
            class="w-full"
          />
        </UFormField>
        <UFormField
          v-if="sorts.length"
          label="Order"
        >
          <USelect
            v-model="sortOrder"
            :items="[{ label: 'Descending', value: 'desc' }, { label: 'Ascending', value: 'asc' }]"
            aria-label="Sort order"
            class="w-full"
          />
        </UFormField>
      </div>
    </div>
  </section>
</template>
