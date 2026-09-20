<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
definePageMeta({ layout: 'auth' })
useSeoMeta({ title: 'Reset password' })
const email = ref('')
const loading = ref(false)
const sent = ref(false)
const errorMessage = ref('')
async function submit() {
  errorMessage.value = ''
  loading.value = true
  try {
    await $fetch('/api/auth/forgot-password', { method: 'POST', body: { email: email.value } })
    sent.value = true
  } catch (error) {
    const candidate = error as { data?: { statusMessage?: string } }
    errorMessage.value = candidate.data?.statusMessage || 'We could not send the reset link. Try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="people-card p-6 sm:p-8">
    <div
      v-if="sent"
      class="text-center"
    >
      <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-[var(--people-mint)]"><UIcon
        name="i-lucide-mail-check"
        class="size-7"
      /></span>
      <h1 class="mt-5 text-2xl font-semibold">
        Check your inbox
      </h1>
      <p class="mt-3 text-sm leading-6 text-muted">
        If an account matches {{ email }}, you’ll receive a password reset link shortly.
      </p>
      <UButton
        to="/login"
        class="mt-7"
        color="neutral"
        variant="soft"
        icon="i-lucide-arrow-left"
      >
        Back to sign in
      </UButton>
    </div>
    <template v-else>
      <p class="text-sm font-semibold text-primary">
        Account recovery
      </p>
      <h1 class="mt-2 text-3xl font-semibold tracking-tight">
        Forgot your password?
      </h1>
      <p class="mt-3 text-sm leading-6 text-muted">
        Enter your work email and we’ll send you a secure reset link.
      </p>
      <form
        class="mt-7 space-y-5"
        @submit.prevent="submit"
      >
        <UFormField
          label="Work email"
          required
        >
          <UInput
            v-model="email"
            class="w-full"
            size="xl"
            type="email"
            autocomplete="email"
            icon="i-lucide-mail"
            placeholder="you@company.com"
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
          Send reset link
        </UButton>
      </form>
      <NuxtLink
        to="/login"
        class="mt-6 flex items-center justify-center gap-2 text-sm font-medium text-muted hover:text-highlighted"
      ><UIcon name="i-lucide-arrow-left" />Back to sign in</NuxtLink>
    </template>
  </section>
</template>
