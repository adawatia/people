<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
definePageMeta({ layout: 'auth' })
useSeoMeta({ title: 'Choose a new password' })
const route = useRoute()
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const complete = ref(false)
const errorMessage = ref('')
async function submit() {
  errorMessage.value = ''
  if (password.value.length < 12) {
    errorMessage.value = 'Use at least 12 characters.'
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMessage.value = 'The passwords do not match.'
    return
  }
  loading.value = true
  try {
    await $fetch('/api/auth/reset-password', { method: 'POST', body: { token: route.query.token, password: password.value } })
    complete.value = true
  } catch (error) {
    const candidate = error as { data?: { statusMessage?: string } }
    errorMessage.value = candidate.data?.statusMessage || 'This reset link is invalid or expired.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="people-card p-6 sm:p-8">
    <div
      v-if="complete"
      class="text-center"
    >
      <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-[var(--people-mint)]"><UIcon
        name="i-lucide-circle-check-big"
        class="size-7"
      /></span>
      <h1 class="mt-5 text-2xl font-semibold">
        Password updated
      </h1>
      <p class="mt-3 text-sm text-muted">
        You can now sign in with your new password.
      </p>
      <UButton
        to="/login"
        class="mt-7"
        icon="i-lucide-log-in"
      >
        Continue to sign in
      </UButton>
    </div>
    <template v-else>
      <p class="text-sm font-semibold text-primary">
        Almost there
      </p>
      <h1 class="mt-2 text-3xl font-semibold tracking-tight">
        Choose a new password
      </h1>
      <p class="mt-3 text-sm leading-6 text-muted">
        Use at least 12 characters with uppercase, lowercase, number and symbol.
      </p>
      <form
        class="mt-7 space-y-5"
        @submit.prevent="submit"
      >
        <UFormField
          label="New password"
          required
        >
          <UInput
            v-model="password"
            class="w-full"
            size="xl"
            type="password"
            autocomplete="new-password"
            icon="i-lucide-lock-keyhole"
          />
        </UFormField>
        <UFormField
          label="Confirm password"
          required
        >
          <UInput
            v-model="confirmPassword"
            class="w-full"
            size="xl"
            type="password"
            autocomplete="new-password"
            icon="i-lucide-lock-keyhole"
          />
        </UFormField>
        <UAlert
          v-if="errorMessage"
          color="error"
          variant="soft"
          :description="errorMessage"
        />
        <UButton
          type="submit"
          block
          size="xl"
          :loading="loading"
        >
          Update password
        </UButton>
      </form>
    </template>
  </section>
</template>
