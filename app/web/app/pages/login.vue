<script setup lang="ts">
import type { FormError, FormErrorEvent } from '@nuxt/ui'
import type { MfaChallenge } from '#shared/types/auth'

definePageMeta({ layout: 'auth' })
useSeoMeta({ title: 'Sign in · Emploi' })
const route = useRoute()
const auth = useAuth()
const form = reactive({ identity: '', password: '' })
const formRef = useTemplateRef('formRef')
const errorMessage = ref('')
const errorTitle = ref('')
const challenge = ref<MfaChallenge | null>(null)
/** Set when /settings sends the user back here after a password change. */
const notice = computed(() => (typeof route.query.notice === 'string' ? route.query.notice : ''))

/**
 * Every workforce role — employee, manager, unit HR, organization HR,
 * organization owner — signs in here. Permissions and scope are resolved after
 * authentication, so the login form never asks what someone is.
 */
function destination() {
  return safeInternalPath(route.query.redirect)
}

function validate(state: { identity?: string, password?: string }): FormError[] {
  const errors: FormError[] = []
  const id = state.identity?.trim() || ''
  if (!id) {
    errors.push({ name: 'identity', message: 'Mobile number or username is required.' })
  } else if (id.includes('@') && id.toLowerCase() !== 'admin@hrms.com') {
    errors.push({ name: 'identity', message: 'Sign in with your mobile number or username, not your email address.' })
  }
  if (!state.password) {
    errors.push({ name: 'password', message: 'Password is required.' })
  }
  return errors
}

function onError(event: FormErrorEvent) {
  if (!form.identity.trim() || !form.password) {
    errorMessage.value = 'Enter your mobile number or username and your password.'
  } else if (event.errors?.[0]?.message) {
    errorMessage.value = event.errors[0].message
  }
}

watch(() => form.identity, () => {
  if (errorMessage.value) {
    errorMessage.value = ''
    errorTitle.value = ''
  }
  formRef.value?.clear('identity')
})
watch(() => form.password, () => {
  if (errorMessage.value) {
    errorMessage.value = ''
    errorTitle.value = ''
  }
  formRef.value?.clear('password')
})

async function submit() {
  if (auth.loading.value) return
  errorMessage.value = ''
  errorTitle.value = ''

  try {
    const result = await auth.login({ ...form, accountType: 'employee' })
    if ('mfa_required' in result) {
      challenge.value = result
      return
    }
    // A temporary password (set by HR or ERP) must be replaced before the
    // person can use the account normally.
    await navigateTo(result.must_change_password ? '/settings?change-password=1' : destination())
  } catch (error) {
    const candidate = error as { data?: { statusMessage?: string, message?: string, detail?: string }, statusMessage?: string, statusCode?: number }
    const status = candidate.statusCode || 401
    const rawMsg = candidate.data?.detail || candidate.data?.statusMessage || candidate.data?.message || candidate.statusMessage || ''

    if (status === 429) {
      errorTitle.value = 'Too many attempts'
      errorMessage.value = rawMsg || 'Too many failed login attempts. Try again in 30 seconds.'
    } else if (status === 403 && typeof rawMsg === 'string' && rawMsg.toLowerCase().includes('technical')) {
      errorTitle.value = 'Technical account'
      errorMessage.value = rawMsg || 'This account is a technical account. Use the technical sign-in.'
    } else {
      errorTitle.value = 'Invalid credentials'
      errorMessage.value = rawMsg || 'The username or password you entered is incorrect. Please try again.'
      formRef.value?.setErrors([{ name: 'password', message: 'Invalid password or username.' }])
    }
  }
}

async function afterMfa() {
  await navigateTo(auth.mustChangePassword.value ? '/settings?change-password=1' : destination())
}
</script>

<template>
  <div>
    <AuthMfaChallenge
      v-if="challenge"
      :mfa-token="challenge.mfa_token"
      :enrollment-required="challenge.enrollment_required"
      account-type="employee"
      @verified="afterMfa"
      @cancelled="challenge = null"
    />
    <template v-else>
      <h1>Sign in to Emploi</h1>
      <UForm
        ref="formRef"
        :state="form"
        :validate="validate"
        class="auth-form"
        :aria-busy="auth.loading.value"
        @submit="submit"
        @error="onError"
      >
        <UFormField
          label="Mobile number or username"
          name="identity"
          required
        >
          <UInput
            v-model="form.identity"
            class="w-full"
            size="xl"
            autocomplete="username"
            placeholder="Enter mobile number or username"
            :autocapitalize="'none'"
            :spellcheck="false"
          />
        </UFormField>
        <UFormField
          label="Password"
          name="password"
          required
        >
          <AuthPasswordInput v-model="form.password" />
        </UFormField>
        <NuxtLink
          to="/forgot-password"
          class="auth-link"
        >Forgot your password?</NuxtLink>
        <div
          v-if="notice === 'password-changed'"
          role="status"
        >
          <UAlert
            color="success"
            variant="soft"
            icon="i-lucide-shield-check"
            description="Your password was changed and every device was signed out. Sign in with your new password."
          />
        </div>
        <div
          v-if="errorMessage"
          role="alert"
        >
          <UAlert
            color="error"
            variant="soft"
            icon="i-lucide-circle-alert"
            :title="errorTitle || undefined"
            :description="errorMessage"
          />
        </div>
        <UButton
          type="submit"
          block
          size="xl"
          :loading="auth.loading.value"
          :disabled="auth.loading.value"
          trailing-icon="i-lucide-arrow-right"
        >
          Sign in
        </UButton>
      </UForm>
      <div class="auth-secondary-links">
        <NuxtLink
          to="/admin/login"
          class="auth-link"
        >Technical administrator sign-in <UIcon
          name="i-lucide-arrow-up-right"
          class="ml-1 size-4"
        /></NuxtLink>
      </div>
    </template>
  </div>
</template>
