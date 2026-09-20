<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
definePageMeta({ layout: 'auth' })
useSeoMeta({ title: 'Verify email' })
const route = useRoute()
const api = useHrmsApi()
const state = ref<'loading' | 'success' | 'error'>('loading')
const message = ref('')
onMounted(async () => {
  const token = String(route.query.token || '')
  if (!token) {
    state.value = 'error'
    message.value = 'The verification token is missing.'
    return
  }
  try {
    await api.request('auth/verify', { method: 'POST', body: { token } })
    state.value = 'success'
  } catch (error) {
    const candidate = error as { data?: { detail?: string, statusMessage?: string } }
    state.value = 'error'
    message.value = candidate.data?.detail || candidate.data?.statusMessage || 'This verification link is invalid or expired.'
  }
})
</script>

<template>
  <section class="people-card p-7 text-center sm:p-9">
    <template v-if="state === 'loading'">
      <UIcon
        name="i-lucide-loader-circle"
        class="mx-auto size-10 animate-spin text-primary"
      /><h1 class="mt-5 text-2xl font-semibold">
        Verifying your email
      </h1><p class="mt-2 text-sm text-muted">
        This should only take a moment.
      </p>
    </template>
    <template v-else-if="state === 'success'">
      <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-[var(--people-mint)]"><UIcon
        name="i-lucide-mail-check"
        class="size-7"
      /></span><h1 class="mt-5 text-2xl font-semibold">
        Email verified
      </h1><p class="mt-2 text-sm text-muted">
        Your email address is confirmed and your account is ready.
      </p><UButton
        to="/login"
        class="mt-7"
        icon="i-lucide-log-in"
      >
        Continue to sign in
      </UButton>
    </template>
    <template v-else>
      <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-[var(--people-rose)]"><UIcon
        name="i-lucide-mail-x"
        class="size-7"
      /></span><h1 class="mt-5 text-2xl font-semibold">
        Verification failed
      </h1><p class="mt-2 text-sm text-muted">
        {{ message }}
      </p><UButton
        to="/login"
        class="mt-7"
        color="neutral"
        variant="soft"
      >
        Back to sign in
      </UButton>
    </template>
  </section>
</template>
