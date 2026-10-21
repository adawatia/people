<script setup lang="ts">
definePageMeta({ layout: 'auth' })
useSeoMeta({ title: 'Recover password · Emploi' })

const identity = ref('')
const code = ref('')
const password = ref('')
const confirmation = ref('')
const recoveryToken = ref('')
const resetToken = ref('')
const step = ref<'identify' | 'verify' | 'reset' | 'done'>('identify')
const errorMessage = ref('')
const loading = ref(false)

const message = (error: unknown) => (error as { data?: { statusMessage?: string, detail?: string }, statusMessage?: string, message?: string }).data?.statusMessage
  || (error as { data?: { detail?: string } }).data?.detail
  || (error as { statusMessage?: string }).statusMessage
  || (error as { message?: string }).message
  || 'We could not complete password recovery.'

function handleRecoveryError(error: unknown) {
  const detail = message(error)
  if (detail.toLowerCase().includes('recovery session')) {
    recoveryToken.value = ''
    resetToken.value = ''
    code.value = ''
    password.value = ''
    confirmation.value = ''
    step.value = 'identify'
    errorMessage.value = 'Your recovery session expired or was replaced. Start again with your mobile number or username.'
    return
  }
  errorMessage.value = detail
}

async function start() {
  if (loading.value) return
  errorMessage.value = ''
  if (!identity.value.trim()) {
    errorMessage.value = 'Enter your mobile number or username.'
    return
  }
  loading.value = true
  try {
    const result = await $fetch<{ recovery_token: string }>('/api/session/password-recovery/start', { method: 'POST', body: { identity: identity.value.trim() } })
    recoveryToken.value = result.recovery_token
    step.value = 'verify'
  } catch (error) {
    errorMessage.value = message(error)
  } finally {
    loading.value = false
  }
}

async function verify() {
  if (loading.value) return
  errorMessage.value = ''
  if (!code.value.trim()) {
    errorMessage.value = 'Enter your authenticator code.'
    return
  }
  loading.value = true
  try {
    const result = await $fetch<{ recovery_token: string }>('/api/session/password-recovery/verify', { method: 'POST', body: { recovery_token: recoveryToken.value, code: code.value.trim() } })
    resetToken.value = result.recovery_token
    step.value = 'reset'
  } catch (error) {
    handleRecoveryError(error)
  } finally {
    loading.value = false
  }
}

async function reset() {
  if (loading.value) return
  errorMessage.value = ''
  if (password.value !== confirmation.value) {
    errorMessage.value = 'The passwords do not match.'
    return
  }
  loading.value = true
  try {
    await $fetch('/api/session/password-recovery/reset', { method: 'POST', body: { reset_token: resetToken.value, new_password: password.value } })
    step.value = 'done'
  } catch (error) {
    handleRecoveryError(error)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <h1>{{ step === 'done' ? 'You’re ready to return.' : 'Reset your password' }}</h1>
    <p class="auth-description">
      Use the authenticator app linked to your Emploi account. Resetting your password signs out your other sessions.
    </p>
    <ol
      class="auth-steps"
      aria-label="Password recovery progress"
    >
      <li :aria-current="step === 'identify' ? 'step' : undefined">
        1. Account
      </li>
      <li :aria-current="step === 'verify' ? 'step' : undefined">
        2. Verify
      </li>
      <li :aria-current="step === 'reset' ? 'step' : undefined">
        3. Password
      </li>
      <li :aria-current="step === 'done' ? 'step' : undefined">
        4. Complete
      </li>
    </ol>
    <div
      v-if="errorMessage"
      role="alert"
    >
      <UAlert
        color="error"
        variant="soft"
        :description="errorMessage"
      />
    </div>
    <form
      v-if="step !== 'done'"
      class="auth-form"
      :aria-busy="loading"
      @submit.prevent="step === 'identify' ? start() : step === 'verify' ? verify() : reset()"
    >
      <UFormField
        v-if="step === 'identify'"
        label="Mobile number or username"
        name="identity"
        required
      >
        <UInput
          v-model="identity"
          class="w-full"
          size="xl"
          autocomplete="username"
          placeholder="Enter mobile number or username"
          :autocapitalize="'none'"
          :spellcheck="false"
        />
      </UFormField>
      <UFormField
        v-else-if="step === 'verify'"
        label="Authenticator code"
        name="code"
        required
      >
        <UInput
          v-model="code"
          class="w-full"
          size="xl"
          inputmode="numeric"
          autocomplete="one-time-code"
          placeholder="Enter 6-digit code"
          autofocus
        />
      </UFormField>
      <template v-else>
        <UFormField
          label="New password"
          name="password"
          required
        >
          <AuthPasswordInput
            v-model="password"
            autocomplete="new-password"
            placeholder="Create your new password"
          />
        </UFormField>
        <UFormField
          label="Confirm new password"
          name="confirmation"
          required
        >
          <AuthPasswordInput
            v-model="confirmation"
            autocomplete="new-password"
            placeholder="Re-enter your new password"
          />
        </UFormField>
      </template>
      <UButton
        type="submit"
        block
        size="xl"
        :loading="loading"
        :disabled="loading"
        trailing-icon="i-lucide-arrow-right"
      >
        {{ step === 'identify' ? 'Continue' : step === 'verify' ? 'Verify authenticator' : 'Set new password' }}
      </UButton>
    </form>
    <div
      v-else
      class="mt-6"
      role="status"
    >
      <UAlert
        color="success"
        variant="soft"
        title="Password changed"
        description="All sessions were ended. Sign in with your new password."
      />
    </div>
    <div class="auth-secondary-links">
      <NuxtLink
        to="/login"
        class="auth-link"
      ><UIcon
        name="i-lucide-arrow-left"
        class="mr-2 size-4"
      />{{ step === 'done' ? 'Return to sign in' : 'Back to sign in' }}</NuxtLink>
    </div>
  </div>
</template>
