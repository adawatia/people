<script setup lang="ts">
import type { MfaChallenge } from '#shared/types/auth'

definePageMeta({ layout: false })
useSeoMeta({ title: 'Technical sign-in' })

/**
 * Super Admin sign-in. Deliberately a different route from /login: the technical
 * identity is not a business role, it is a break-glass account with a stricter
 * session policy and (once enrolled) a mandatory second factor. Business users
 * never see this page, and a business account cannot authenticate here.
 */
const auth = useAuth()
const form = reactive({ identity: '', password: '' })
const errorMessage = ref('')
const challenge = ref<MfaChallenge | null>(null)

async function submit() {
  errorMessage.value = ''
  if (!form.identity.trim() || !form.password) {
    errorMessage.value = 'Enter the technical username and password.'
    return
  }
  try {
    const result = await auth.login({ ...form, accountType: 'super_admin' })
    if ('mfa_required' in result) {
      challenge.value = result
      return
    }
    await navigateTo(result.must_change_password ? '/settings?change-password=1' : '/')
  } catch (error) {
    const candidate = error as { data?: { statusMessage?: string, message?: string }, statusMessage?: string }
    errorMessage.value = candidate.data?.statusMessage || candidate.data?.message || candidate.statusMessage || 'Those credentials were not accepted.'
  }
}

async function afterMfa() {
  await navigateTo(auth.mustChangePassword.value ? '/settings?change-password=1' : '/')
}
</script>

<template>
  <div class="flex min-h-dvh items-center justify-center bg-[#14121f] px-5 py-12">
    <div class="w-full max-w-md">
      <div class="flex items-center gap-3">
        <span class="grid size-10 place-items-center rounded-xl bg-white/10 text-white">
          <UIcon
            name="i-lucide-shield-half"
            class="size-5"
          />
        </span>
        <div>
          <p class="text-sm font-semibold text-white">
            Technical administration
          </p>
          <p class="text-xs text-white/60">
            People HRMS
          </p>
        </div>
      </div>

      <div class="mt-8 rounded-2xl bg-white p-6 shadow-xl sm:p-8">
        <template v-if="challenge">
          <AuthMfaChallenge
            :mfa-token="challenge.mfa_token"
            :enrollment-required="challenge.enrollment_required"
            account-type="super_admin"
            @verified="afterMfa"
            @cancelled="challenge = null"
          />
        </template>
        <template v-else>
          <h1 class="text-2xl font-semibold tracking-tight">
            Technical sign-in
          </h1>
          <p class="mt-2 text-sm leading-6 text-muted">
            Restricted to system administrators. Business users sign in from the employee page.
          </p>
          <UAlert
            class="mt-5"
            color="warning"
            variant="soft"
            icon="i-lucide-triangle-alert"
            description="Sign-ins and session changes on this account are audited. Sessions expire quickly and require a second factor once enrolled."
          />
          <form
            class="mt-6 space-y-5"
            @submit.prevent="submit"
          >
            <UFormField
              label="Username"
              name="identity"
              required
            >
              <UInput
                v-model="form.identity"
                class="w-full"
                size="xl"
                icon="i-lucide-user-round-cog"
                autocomplete="username"
                placeholder="Enter username"
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
                type="password"
                autocomplete="current-password"
                placeholder="Enter your password"
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
              color="neutral"
              icon="i-lucide-log-in"
              :loading="auth.loading.value"
            >
              Sign in
            </UButton>
          </form>
        </template>
      </div>

      <NuxtLink
        to="/login"
        class="mt-6 block text-center text-xs text-white/60 hover:text-white"
      >
        Employee sign-in
      </NuxtLink>
    </div>
  </div>
</template>
