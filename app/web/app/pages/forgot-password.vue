<script setup lang="ts">
definePageMeta({ layout: false })
useSeoMeta({ title: 'Recover password' })

const identity = ref('')
const code = ref('')
const password = ref('')
const confirmation = ref('')
const recoveryToken = ref('')
const resetToken = ref('')
const step = ref<'identify' | 'verify' | 'reset' | 'done'>('identify')
const errorMessage = ref('')
const loading = ref(false)

const message = (error: unknown) => (error as { data?: { statusMessage?: string, detail?: string }, statusMessage?: string }).data?.statusMessage
  || (error as { data?: { detail?: string } }).data?.detail
  || (error as { statusMessage?: string }).statusMessage
  || 'We could not complete password recovery.'

async function start() {
  errorMessage.value = ''
  if (!identity.value.trim()) { errorMessage.value = 'Enter your mobile number or username.'; return }
  loading.value = true
  try {
    const result = await $fetch<{ recovery_token: string }>('/api/session/password-recovery/start', { method: 'POST', body: { identity: identity.value.trim() } })
    recoveryToken.value = result.recovery_token
    step.value = 'verify'
  } catch (error) { errorMessage.value = message(error) } finally { loading.value = false }
}

async function verify() {
  errorMessage.value = ''
  loading.value = true
  try {
    const result = await $fetch<{ recovery_token: string }>('/api/session/password-recovery/verify', { method: 'POST', body: { recovery_token: recoveryToken.value, code: code.value.trim() } })
    resetToken.value = result.recovery_token
    step.value = 'reset'
  } catch (error) { errorMessage.value = message(error) } finally { loading.value = false }
}

async function reset() {
  errorMessage.value = ''
  if (password.value !== confirmation.value) { errorMessage.value = 'The passwords do not match.'; return }
  loading.value = true
  try {
    await $fetch('/api/session/password-recovery/reset', { method: 'POST', body: { reset_token: resetToken.value, new_password: password.value } })
    step.value = 'done'
  } catch (error) { errorMessage.value = message(error) } finally { loading.value = false }
}
</script>

<template>
  <main class="grid min-h-dvh place-items-center bg-[var(--people-canvas)] px-5 py-10">
    <section class="w-full max-w-md people-card space-y-6 p-6 sm:p-8">
      <div>
        <p class="text-sm font-semibold text-primary">Account recovery</p>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight">Reset your password</h1>
        <p class="mt-3 text-sm leading-6 text-muted">Use the authenticator app linked to your People account. Your sessions will be signed out after the reset.</p>
      </div>
      <UAlert v-if="errorMessage" color="error" variant="soft" :description="errorMessage" />
      <template v-if="step === 'identify'">
        <UFormField label="Mobile number or username" name="identity">
          <UInput v-model="identity" class="w-full" autocomplete="username" placeholder="9876543210" autofocus />
        </UFormField>
        <UButton block size="lg" :loading="loading" @click="start">Continue</UButton>
      </template>
      <template v-else-if="step === 'verify'">
        <UFormField label="Authenticator code" name="code">
          <UInput v-model="code" class="w-full" inputmode="numeric" autocomplete="one-time-code" placeholder="123456" autofocus />
        </UFormField>
        <UButton block size="lg" :loading="loading" @click="verify">Verify authenticator</UButton>
      </template>
      <template v-else-if="step === 'reset'">
        <UFormField label="New password" name="password">
          <UInput v-model="password" class="w-full" type="password" autocomplete="new-password" />
        </UFormField>
        <UFormField label="Confirm new password" name="confirmation">
          <UInput v-model="confirmation" class="w-full" type="password" autocomplete="new-password" />
        </UFormField>
        <UButton block size="lg" :loading="loading" @click="reset">Set new password</UButton>
      </template>
      <template v-else>
        <UAlert color="success" variant="soft" title="Password changed" description="All sessions were ended. Sign in with your new password." />
        <NuxtLink to="/login" class="block text-center font-medium text-primary hover:underline">Return to sign in</NuxtLink>
      </template>
      <NuxtLink to="/login" class="block text-center text-sm text-muted hover:underline">Back to sign in</NuxtLink>
    </section>
  </main>
</template>
