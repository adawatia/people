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
const { isDesktop } = useIsDesktop()
const code = ref('')
const errorMessage = ref('')
const enrollment = ref<MfaEnrollment | null>(null)
const loadingEnrollment = ref(false)

async function loadEnrollment() {
  if (!props.enrollmentRequired || !isDesktop.value || enrollment.value) return
  loadingEnrollment.value = true
  try {
    enrollment.value = await auth.startMfaEnrollment(props.mfaToken)
  } catch {
    errorMessage.value = 'We could not start authenticator setup. Sign in again to retry.'
  } finally {
    loadingEnrollment.value = false
  }
}

onMounted(() => {
  if (props.enrollmentRequired && isDesktop.value) {
    void loadEnrollment()
  }
})

watch(isDesktop, (val) => {
  if (val && props.enrollmentRequired && !enrollment.value) {
    void loadEnrollment()
  }
})

async function submit() {
  if (auth.loading.value || loadingEnrollment.value) return
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
      <h1>
        {{ enrollmentRequired ? 'Add a second factor' : 'Enter your code' }}
      </h1>
      <p class="auth-description">
        <template v-if="enrollmentRequired">
          <template v-if="isDesktop">
            This account requires two-step verification. Scan the QR code with your authenticator app, then confirm with the code it shows.
          </template>
          <template v-else>
            This account requires two-step verification, which must be set up from a desktop computer.
          </template>
        </template>
        <template v-else>
          Open your authenticator app and enter the current 6-digit code. A single-use recovery code works too.
        </template>
      </p>
    </div>

    <!-- Mobile prompt for enrollment -->
    <div
      v-if="enrollmentRequired && !isDesktop"
      class="space-y-4 rounded-xl border border-[var(--people-border)] p-5 text-center"
    >
      <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <UIcon
          name="i-lucide-monitor"
          class="size-6"
        />
      </div>
      <div class="space-y-1">
        <h2 class="text-base font-semibold">
          Desktop required for setup
        </h2>
        <p class="text-sm text-muted">
          Two-step verification must be set up on a desktop computer so you can easily scan the QR code with your mobile authenticator app and save your recovery keys.
        </p>
      </div>
      <p class="text-xs text-muted">
        Please sign in from a desktop browser to complete setup. Once enrolled, you can sign in from any device.
      </p>
      <div class="pt-2">
        <UButton
          type="button"
          block
          variant="outline"
          size="lg"
          icon="i-lucide-arrow-left"
          @click="emit('cancelled')"
        >
          Back to sign in
        </UButton>
      </div>
    </div>

    <!-- Desktop enrollment or regular MFA verification -->
    <template v-else>
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
          <MfaRecoveryCodes :codes="recoveryCodes" />
        </template>
      </div>

      <form
        class="auth-form"
        :aria-busy="auth.loading.value"
        @submit.prevent="submit"
      >
        <UFormField
          label="Authenticator or recovery code"
          name="code"
          required
        >
          <UInput
            v-model="code"
            class="w-full"
            size="xl"
            icon="i-lucide-shield-check"
            autocomplete="one-time-code"
            placeholder="Enter your code"
            :autocapitalize="'none'"
            :spellcheck="false"
            autofocus
          />
        </UFormField>
        <div
          v-if="errorMessage"
          role="alert"
        >
          <UAlert
            color="error"
            variant="soft"
            icon="i-lucide-circle-alert"
            :description="errorMessage"
          />
        </div>
        <UButton
          type="submit"
          block
          size="xl"
          icon="i-lucide-log-in"
          :loading="auth.loading.value"
          :disabled="auth.loading.value || loadingEnrollment || (enrollmentRequired && !enrollment)"
        >
          {{ enrollmentRequired ? 'Confirm and sign in' : 'Verify and sign in' }}
        </UButton>
        <UButton
          type="button"
          block
          variant="ghost"
          size="lg"
          :disabled="auth.loading.value"
          @click="emit('cancelled')"
        >
          Back to sign in
        </UButton>
      </form>
    </template>
  </div>
</template>
