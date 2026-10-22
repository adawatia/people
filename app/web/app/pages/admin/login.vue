<script setup lang="ts">
import type { FormError, FormErrorEvent } from '@nuxt/ui'
import type { MfaChallenge } from '#shared/types/auth'

definePageMeta({ layout: 'auth' })
useSeoMeta({ title: 'Technical sign-in · Emploi' })

/**
 * Super Admin sign-in. Deliberately a different route from /login: the technical
 * identity is not a business role, it is a break-glass account with a stricter
 * session policy and (once enrolled) a mandatory second factor. Business users
 * never see this page, and a business account cannot authenticate here.
 */
const route = useRoute()
const auth = useAuth()
const form = reactive({ identity: '', password: '' })
const formRef = useTemplateRef('formRef')
const errorMessage = ref('')
const errorTitle = ref('')
const challenge = ref<MfaChallenge | null>(null)
/** Set when /settings sends the user back here after a password change. */
const notice = computed(() => (typeof route.query.notice === 'string' ? route.query.notice : ''))

function destination() {
  return safeInternalPath(route.query.redirect)
}

function validate(state: { identity?: string, password?: string }): FormError[] {
  const errors: FormError[] = []
  const id = state.identity?.trim() || ''
  if (!id) {
    errors.push({ name: 'identity', message: 'Technical username is required.' })
  } else if (id.includes('@') || id.startsWith('+') || /^\d+$/.test(id)) {
    errors.push({
      name: 'identity',
      message: 'Sign in with your technical username (not an email or mobile number).'
    })
  }
  if (!state.password) {
    errors.push({ name: 'password', message: 'Password is required.' })
  }
  return errors
}

function onError(event: FormErrorEvent) {
  if (!form.identity.trim() || !form.password) {
    errorMessage.value = 'Enter the technical username and password.'
  } else if (event.errors?.[0]?.message) {
    errorMessage.value = event.errors[0].message
  }
}

watch(() => form.identity, () => {
  if (errorMessage.value) {
    errorMessage.value = ''
    errorTitle.value = ''
  }
  formRef.value?.clear()
})
watch(() => form.password, () => {
  if (errorMessage.value) {
    errorMessage.value = ''
    errorTitle.value = ''
  }
  formRef.value?.clear()
})

async function submit() {
  if (auth.loading.value) return
  errorMessage.value = ''
  errorTitle.value = ''

  try {
    const result = await auth.login({ ...form, accountType: 'super_admin' })
    if ('mfa_required' in result) {
      challenge.value = result
      return
    }
    await navigateTo(result.must_change_password ? '/settings?change-password=1' : destination())
  } catch (error) {
    const candidate = error as { data?: { statusMessage?: string, message?: string, detail?: string }, statusMessage?: string, statusCode?: number }
    const status = candidate.statusCode || 401
    const rawMsg = candidate.data?.detail || candidate.data?.statusMessage || candidate.data?.message || candidate.statusMessage || ''

    if (status === 429) {
      errorTitle.value = 'Too many attempts'
      errorMessage.value = rawMsg || 'Too many failed login attempts. Try again in 30 seconds.'
    } else {
      errorTitle.value = 'Invalid credentials'
      errorMessage.value = rawMsg || 'Those credentials were not accepted. Passwords are case-sensitive.'
      formRef.value?.setErrors([
        { name: 'identity', message: 'Check your technical username.' },
        { name: 'password', message: 'Invalid password or username.' }
      ])
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
      account-type="super_admin"
      @verified="afterMfa"
      @cancelled="challenge = null"
    />
    <template v-else>
      <h1>Technical administration</h1>
      <p class="auth-description">
        Restricted to system administrators. For workforce access, use employee sign-in.
      </p>
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
          label="Technical username"
          name="identity"
          required
        >
          <UInput
            v-model="form.identity"
            class="w-full"
            size="xl"
            autocomplete="username"
            placeholder="Enter technical username"
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
            :actions="errorTitle === 'Invalid credentials' ? [{ label: 'Employee sign-in', to: '/login' }] : undefined"
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
          Sign in to administration
        </UButton>
      </UForm>
      <p class="auth-security-note">
        Technical sign-ins are audited. A second factor is required once enrolled.
      </p>
      <div class="auth-secondary-links">
        <NuxtLink
          to="/login"
          class="auth-link"
        ><UIcon
          name="i-lucide-arrow-left"
          class="mr-2 size-4"
        />Employee sign-in</NuxtLink>
      </div>
    </template>
  </div>
</template>
