<script setup lang="ts">
import type { MfaChallenge } from '#shared/types/auth'

definePageMeta({ layout: false })
useSeoMeta({ title: 'Sign in' })
const route = useRoute()
const auth = useAuth()
const form = reactive({ identity: '', password: '' })
const errorMessage = ref('')
const showPassword = ref(false)
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
  errorMessage.value = ''
  if (!form.identity.trim() || !form.password) {
    errorMessage.value = 'Enter your mobile number, email or username and your password.'
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
  <div class="grid min-h-dvh bg-[var(--people-canvas)] lg:grid-cols-[1.05fr_0.95fr]">
    <section class="relative hidden overflow-hidden bg-[#27213f] p-12 text-white lg:flex lg:flex-col lg:justify-between">
      <div class="absolute -left-20 top-32 size-80 rounded-full bg-violet-400/20 blur-3xl" />
      <div class="absolute -bottom-24 right-0 size-96 rounded-full bg-sky-300/15 blur-3xl" />
      <BrandMark class="relative z-10 [&_.text-muted]:text-violet-100/60" />
      <div class="relative z-10 max-w-xl pb-10">
        <div class="mb-6 flex gap-2">
          <span class="h-2 w-12 rounded-full bg-violet-300" /><span class="h-2 w-5 rounded-full bg-emerald-200" /><span class="h-2 w-5 rounded-full bg-amber-200" />
        </div>
        <h1 class="text-5xl font-semibold leading-[1.08] tracking-tight">
          Work feels simpler when everything is in one place.
        </h1>
        <p class="mt-6 max-w-lg text-lg leading-8 text-violet-100/80">
          Attendance, leave, schedules and your team—calmly organized for every workday.
        </p>
      </div>
      <p class="relative z-10 text-sm text-violet-100/60">
        A Datlabs product
      </p>
    </section>
    <section class="flex items-center justify-center px-5 py-10 sm:px-10">
      <div class="w-full max-w-md">
        <BrandMark class="mb-12 lg:hidden" />
        <template v-if="challenge">
          <AuthMfaChallenge
            :mfa-token="challenge.mfa_token"
            :enrollment-required="challenge.enrollment_required"
            account-type="employee"
            @verified="afterMfa"
            @cancelled="challenge = null"
          />
        </template>
        <template v-else>
          <p class="text-sm font-semibold text-primary">
            Welcome back
          </p>
          <h2 class="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
            Sign in to People
          </h2>
          <p class="mt-3 text-sm leading-6 text-muted">
            Use your mobile number, email address or username.
          </p>
          <form
            class="mt-9 space-y-5"
            @submit.prevent="submit"
          >
            <UFormField
              label="Mobile number, email or username"
              name="identity"
              required
            >
              <UInput
                v-model="form.identity"
                class="w-full"
                size="xl"
                icon="i-lucide-user-round"
                autocomplete="username"
                placeholder="9876543210"
                autofocus
              />
            </UFormField>
            <UFormField
              label="Password"
              name="password"
              required
            >
              <UInput
                v-model="form.password"
                class="w-full"
                size="xl"
                icon="i-lucide-lock-keyhole"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="Enter your password"
              >
                <template #trailing>
                  <button
                    type="button"
                    class="grid size-8 place-items-center text-muted hover:text-highlighted"
                    :aria-label="showPassword ? 'Hide password' : 'Show password'"
                    @click="showPassword = !showPassword"
                  >
                    <UIcon
                      :name="showPassword ? 'i-lucide-eye-off' : 'i-lucide-eye'"
                      class="size-4"
                    />
                  </button>
                </template>
              </UInput>
            </UFormField>
            <UAlert
              v-if="notice === 'password-changed'"
              color="success"
              variant="soft"
              icon="i-lucide-shield-check"
              description="Your password was changed and every device was signed out. Sign in again with your new password."
            />
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
              Sign in
            </UButton>
          </form>
          <div class="mt-8 flex flex-col items-center gap-2 text-xs text-muted">
            <NuxtLink
              to="/admin/login"
              class="font-medium text-primary hover:underline"
            >
              Technical administrator sign-in
            </NuxtLink>
            <span>Password reset: contact HR</span>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>
