<script setup lang="ts">
import { useAttrs } from 'vue'

withDefaults(defineProps<{
  autocomplete?: string
  placeholder?: string
  disabled?: boolean
}>(), {
  autocomplete: 'current-password',
  placeholder: 'Enter your password',
  disabled: false
})

const attrs = useAttrs()
const model = defineModel<string>({ required: true })
const visible = ref(false)
</script>

<template>
  <UInput
    v-model="model"
    class="w-full"
    size="xl"
    :type="visible ? 'text' : 'password'"
    :autocomplete="autocomplete"
    :placeholder="placeholder"
    :disabled="disabled"
    :ui="{ trailing: 'pe-1' }"
  >
    <template #trailing>
      <UButton
        color="neutral"
        variant="link"
        size="sm"
        type="button"
        class="auth-password-toggle cursor-pointer"
        :icon="visible ? 'i-lucide-eye-off' : 'i-lucide-eye'"
        :aria-label="visible ? 'Hide password' : 'Show password'"
        :aria-pressed="visible"
        :aria-controls="(attrs.id as string) || 'password'"
        :disabled="disabled"
        @mousedown.prevent
        @click="visible = !visible"
      />
    </template>
  </UInput>
</template>

<style>
/* Hide the password reveal and clear buttons in Edge / IE */
input::-ms-reveal,
input::-ms-clear {
  display: none !important;
}
</style>
