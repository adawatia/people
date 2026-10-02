<script setup lang="ts">
withDefaults(defineProps<{ autocomplete?: string, placeholder?: string }>(), {
  autocomplete: 'current-password',
  placeholder: 'Enter your password'
})
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
  >
    <template #trailing>
      <button
        type="button"
        class="auth-password-toggle"
        :aria-label="visible ? 'Hide password' : 'Show password'"
        :aria-pressed="visible"
        @click="visible = !visible"
      >
        <UIcon
          :name="visible ? 'i-lucide-eye-off' : 'i-lucide-eye'"
          class="size-5"
        />
      </button>
    </template>
  </UInput>
</template>
