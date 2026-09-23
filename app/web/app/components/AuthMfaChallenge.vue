<script setup lang="ts">
import type { MfaEnrollment } from '#shared/types/auth'

/**
 * Second step of sign-in: verify an authenticator code, or complete first-time
 * enrolment. Used by /login and /admin/login so both domains share one
 * implementation — the API decides which accounts need a second factor.
 */
const props = defineProps<{ mfaToken: string, enrollmentRequired: boolean, accountType?: 'employee' | 'super_admin' }>()
const emit = defineEmits<{ verified: [user: object], cancelled: [] }>()

const auth = useAuth()
const code = ref('')
const errorMessage = ref('')
const enrollment = ref<MfaEnrollment | null>(null)
const loadingEnrollment = ref(false)

async function loadEnrollment() {
  if (!props.enrollmentRequired) return
  loadingEnrollment.value = true
  try {
    enrollment.value = await auth.startMfaEnrollment(props.mfaToken)
  } catch {
    errorMessage.value = 'We could not start authenticator setup. Sign in again to retry.'
  } finally {
    loadingEnrollment.value = false
  }
}
onMounted(loadEnrollment)

async function submit() {
  errorMessage.value = ''
  if (!code.value.trim()) {
    errorMessage.value = 'Enter the 6-digit code from your authenticator app.'
    return
  }
  try {
    const user = await auth.completeMfa({
      mfa_token: props.mfaToken,
      code: code.value.trim(),
      enrollment: props.enrollmentRequired
    })
    emit('verified', user as object)
  } catch (error) {
    const candidate = error as { data?: { statusMessage?: string, message?: string }, statusMessage?: string }
    errorMessage.value = candidate.data?.statusMessage || candidate.data?.message || candidate.statusMessage || 'That code was not accepted.'
  }
}

const recoveryCodes = computed(() => enrollment.value?.recovery_codes ?? [])
</script>

<template>
  <div class="space-y-6">
    <div>
      <p class="text-sm font-semibold text-primary">
        {{ enrollmentRequired ? 'Set up your authenticator' : 'Two-step verification' }}
      </p>
      <h3 class="mt-2 text-2xl font-semibold tracking-tight">
        {{ enrollmentRequired ? 'Add a second factor' : 'Enter your code' }}
      </h3>
      <p class="mt-2 text-sm leading-6 text-muted">
        <template v-if="enrollmentRequired">
          This account requires two-step verification. Scan the QR code with your authenticator app, then confirm with the code it shows.
        </template>
        <template v-else>
          Open your authenticator app and enter the current 6-digit code. A single-use recovery code works too.
        </template>
      </p>
    </div>

    <div
      v-if="enrollmentRequired"
      class="space-y-4 rounded-xl border border-[var(--people-border)] p-4"
    >
      <p
        v-if="loadingEnrollment"
        class="text-sm text-muted"
      >
        Preparing your secret…
      </p>
      <template v-else-if="enrollment">
        <MfaQrCode
          :uri="enrollment.otpauth_uri"
          :secret="enrollment.secret"
        />
        <div v-if="recoveryCodes.length">
          <p class="text-xs font-medium uppercase tracking-wide text-muted">
            Recovery codes (shown once)
          </p>
          <div class="mt-2 grid grid-cols-2 gap-1 font-mono text-xs">
            <span
              v-for="recovery in recoveryCodes"
              :key="recovery"
            >{{ recovery }}</span>
          </div>
          <p class="mt-2 text-xs text-muted">
            Store these somewhere safe. Each one signs you in once if you lose your device.
          </p>
        </div>
      </template>
    </div>

    <form
      class="space-y-5"
      @submit.prevent="submit"
    >
      <UFormField
        label="Authentication code"
        name="code"
        required
      >
        <UInput
          v-model="code"
          class="w-full"
          size="xl"
          icon="i-lucide-shield-check"
          inputmode="numeric"
          autocomplete="one-time-code"
          placeholder="123456"
          autofocus
        />
      </UFormField>
      <UAlert
        v-if="errorMessage"
        color="error"
        variant="soft"
        icon="i-lucide-circle-alert"
        :description="errorMessage"
      />
      <UButton
        type="submit"
        block
        size="xl"
        icon="i-lucide-log-in"
        :loading="auth.loading.value"
      >
        {{ enrollmentRequired ? 'Confirm and sign in' : 'Verify and sign in' }}
      </UButton>
      <UButton
        type="button"
        block
        variant="ghost"
        size="sm"
        @click="emit('cancelled')"
      >
        Back to sign in
      </UButton>
    </form>
  </div>
</template>
