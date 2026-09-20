<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes */
definePageMeta({ layout: 'auth' })
useSeoMeta({ title: 'Accept invitation' })
interface Invitation { valid: boolean, email?: string, username?: string, first_name?: string, last_name?: string, role_name?: string, detail?: string }
const route = useRoute()
const api = useHrmsApi()
const token = computed(() => String(route.query.token || ''))
const password = ref('')
const confirmation = ref('')
const submitting = ref(false)
const complete = ref(false)
const errorMessage = ref('')
const { data, pending } = await useAsyncData('invitation', () => token.value
  ? api.request<Invitation>('auth/invitation/validate', { query: { token: token.value } })
  : Promise.resolve({ valid: false, detail: 'The invitation token is missing.' }), { watch: [token] })
const validPassword = computed(() => password.value.length >= 12 && /[A-Z]/.test(password.value) && /[a-z]/.test(password.value) && /\d/.test(password.value) && /[^A-Za-z0-9]/.test(password.value))
async function submit() {
  errorMessage.value = ''
  if (!validPassword.value) return void (errorMessage.value = 'Use 12+ characters with uppercase, lowercase, number and symbol.')
  if (password.value !== confirmation.value) return void (errorMessage.value = 'The passwords do not match.')
  submitting.value = true
  try {
    await api.request('auth/invitation/set-password', { method: 'POST', body: { token: token.value, password: password.value } })
    complete.value = true
  } catch (error) {
    const candidate = error as { data?: { detail?: string | { reason?: string }, statusMessage?: string } }
    errorMessage.value = typeof candidate.data?.detail === 'object' ? candidate.data.detail.reason || 'Could not accept invitation.' : candidate.data?.detail || candidate.data?.statusMessage || 'Could not accept invitation.'
  } finally { submitting.value = false }
}
</script>

<template>
  <section class="people-card p-6 sm:p-8">
    <div
      v-if="pending"
      class="space-y-4"
    >
      <USkeleton class="h-7 w-2/3" /><USkeleton class="h-4 w-full" /><USkeleton class="h-12 w-full" />
    </div>
    <div
      v-else-if="complete"
      class="text-center"
    >
      <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-[var(--people-mint)]"><UIcon
        name="i-lucide-badge-check"
        class="size-7"
      /></span>
      <h1 class="mt-5 text-2xl font-semibold">
        Your account is ready
      </h1>
      <p class="mt-3 text-sm text-muted">
        Your password has been created. Sign in to open People.
      </p>
      <UButton
        to="/login"
        class="mt-7"
        size="lg"
        icon="i-lucide-log-in"
      >
        Continue to sign in
      </UButton>
    </div>
    <UAlert
      v-else-if="!data?.valid"
      color="error"
      variant="soft"
      icon="i-lucide-link-2-off"
      title="Invitation unavailable"
      :description="data?.detail || 'This invitation is invalid or expired.'"
    />
    <template v-else>
      <p class="text-sm font-semibold text-primary">
        Welcome to People
      </p>
      <h1 class="mt-2 text-3xl font-semibold tracking-tight">
        Create your password
      </h1>
      <p class="mt-3 text-sm leading-6 text-muted">
        Hi {{ data.first_name || data.username }}. Complete your {{ data.role_name || 'employee' }} account for {{ data.email }}.
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
            v-model="confirmation"
            class="w-full"
            size="xl"
            type="password"
            autocomplete="new-password"
            icon="i-lucide-shield-check"
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
          :loading="submitting"
        >
          Create account password
        </UButton>
      </form>
    </template>
  </section>
</template>
