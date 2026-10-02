<script setup lang="ts">
withDefaults(defineProps<{ placeholder?: string, clearLabel?: string }>(), { placeholder: 'Search records', clearLabel: 'Clear search' })
const model = defineModel<string>({ default: '' })
const input = useTemplateRef('input')
function focus() {
  input.value?.inputRef?.focus()
}
defineExpose({ focus })
async function clearSearch() {
  model.value = ''
  await nextTick()
  focus()
}
</script>

<template>
  <UInput
    ref="input"
    v-model="model"
    icon="i-lucide-search"
    type="search"
    :placeholder="placeholder"
    autocomplete="off"
    class="w-full"
    :ui="{ trailing: 'pe-0' }"
  >
    <template
      v-if="model"
      #trailing
    >
      <UButton
        type="button"
        icon="i-lucide-x"
        color="neutral"
        variant="ghost"
        :aria-label="clearLabel"
        class="min-h-11 min-w-11 justify-center"
        @click="clearSearch"
      />
    </template>
  </UInput>
</template>
