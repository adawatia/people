<script setup lang="ts">
import type { MfaChallenge } from '#shared/types/auth'

definePageMeta({ layout: 'auth' })
useSeoMeta({ title: 'Sign in · People by Datlabs' })
const route = useRoute()
const auth = useAuth()
const form = reactive({ identity: '', password: '' })
const errorMessage = ref('')
const challenge = ref<MfaChallenge | null>(null)
/** Set when /settings sends the user back here after a password change. */
const notice = computed(() => (typeof route.query.notice === 'string' ? route.query.notice : ''))

/**
 * Every workforce role — employee, manager, unit HR, organization HR,
 * organization owner — signs in here. Permissions and scope are resolved after
 * authentication, so the login form never asks what someone is.
 */
function destination() {
  const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/'
  return redirect
}

async function submit() {
  if (auth.loading.value) return
  errorMessage.value = ''
  if (!form.identity.trim() || !form.password) {
    errorMessage.value = 'Enter your mobile number or username and your password.'
    return
  }
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
    const candidate = error as { data?: { statusMessage?: string, message?: string }, statusMessage?: string }
    errorMessage.value = candidate.data?.statusMessage || candidate.data?.message || candidate.statusMessage || 'We could not sign you in. Check your details and try again.'
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
      <h1>Sign in to People</h1>
      <form
        class="auth-form"
        :aria-busy="auth.loading.value"
        @submit.prevent="submit"
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
      </form>
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
