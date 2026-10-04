<script setup lang="ts">
const props = withDefaults(defineProps<{
  active?: boolean
  activeCount?: number
  sorts?: { label: string, value: string }[]
  searchPlaceholder?: string
  label?: string
}>(), {
  active: false,
  activeCount: 0,
  sorts: () => [],
  searchPlaceholder: 'Search records'
})
const search = defineModel<string>('search', { default: '' })
const sortBy = defineModel<string>('sortBy', { default: '' })
const sortOrder = defineModel<string>('sortOrder', { default: 'desc' })
const emit = defineEmits<{ clear: [] }>()
const slots = useSlots()
const expanded = ref(false)
const searchField = useTemplateRef('searchField')
const panelId = `list-filters-${useId()}`
const hasAdvanced = computed(() => Boolean(props.sorts.length || slots.default))
const activeLabel = computed(() => `${props.activeCount || 1} active`)

watch(() => props.active, (active) => {
  if (active && hasAdvanced.value) expanded.value = true
})

async function clear() {
  emit('clear')
  expanded.value = false
  await nextTick()
  searchField.value?.focus()
}
</script>

<template>
  <section
    class="people-card my-5 overflow-hidden"
    aria-label="List filters"
  >
    <div
      v-if="label || active"
      class="flex items-center justify-between gap-3 border-b border-[var(--people-border)] px-4 py-3 sm:px-5"
    >
      <div class="flex min-w-0 items-center gap-2">
        <span class="grid size-8 shrink-0 place-items-center rounded-lg bg-[var(--people-lavender)] text-primary">
          <UIcon
            name="i-lucide-list-filter"
            class="size-4"
          />
        </span>
        <p
          v-if="label"
          class="min-w-0 truncate text-sm font-semibold"
        >
          {{ label }}
        </p>
        <UBadge
          v-if="active"
          color="primary"
          variant="soft"
          size="sm"
        >
          {{ activeLabel }}
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
        Reset filters
      </UButton>
    </div>

    <div class="p-4 sm:p-5">
      <div class="flex items-center gap-2">
        <UFormField
          label="Search"
          class="min-w-0 flex-1"
        >
          <SearchInput
            ref="searchField"
            v-model="search"
            :placeholder="searchPlaceholder"
            autocomplete="off"
            class="w-full"
          />
        </UFormField>
        <UButton
          v-if="hasAdvanced"
          class="mt-6 min-h-11"
          color="neutral"
          variant="outline"
          :icon="expanded ? 'i-lucide-chevron-up' : 'i-lucide-sliders-horizontal'"
          :aria-expanded="expanded"
          :aria-controls="panelId"
          @click="expanded = !expanded"
        >
          {{ expanded ? 'Hide' : 'Filters' }}
        </UButton>
      </div>

      <div
        v-if="slots.quick"
        class="mt-3 flex flex-wrap items-center gap-2"
        aria-label="Quick filters"
      >
        <slot name="quick" />
      </div>

      <div
        v-if="hasAdvanced"
        :id="panelId"
        class="mt-4 grid gap-3 border-t border-[var(--people-border)] pt-4 md:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]"
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
