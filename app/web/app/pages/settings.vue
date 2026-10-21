<script setup lang="ts">
import type { MfaEnrollment, MfaRecoveryCodes, MfaStatus, SessionSummary } from '#shared/types/auth'

const auth = useAuth()
const api = useHrmsApi()
const toast = useToast()
const route = useRoute()
const isTechnicalAdmin = computed(() => Boolean(auth.user.value?.is_superuser))
const pageTitle = computed(() => isTechnicalAdmin.value ? 'System administration' : 'Security settings')
useSeoMeta({ title: () => pageTitle.value })

const username = ref(auth.user.value?.username || '')
const usernamePassword = ref('')
const currentPassword = ref('')
const newPassword = ref('')
const savingUsername = ref(false)
const usernameError = ref('')
const savingPassword = ref(false)
const passwordError = ref('')
/** Set when HR/ERP issued a temporary password, or login redirected here. */
const passwordChangeRequired = computed(() => auth.mustChangePassword.value || route.query['change-password'] === '1')

const message = (error: unknown) => (error as { data?: { detail?: string, statusMessage?: string } }).data?.detail || (error as { data?: { statusMessage?: string } }).data?.statusMessage || 'Could not save the change.'

async function saveUsername() {
  if (savingUsername.value) return
  usernameError.value = ''
  if (!usernamePassword.value) {
    usernameError.value = 'Enter your current password to change your username.'
    toast.add({ title: 'Enter your current password', description: 'Changing the technical username is a credential change and requires re-verification.', color: 'error' })
    return
  }
  savingUsername.value = true
  try {
    const result = await api.request<{ username: string }>('auth/super-admin/username', {
      method: 'PATCH',
      body: { username: username.value.trim(), current_password: usernamePassword.value }
    })
    if (auth.user.value) auth.user.value.username = result.username
    usernamePassword.value = ''
    toast.add({ title: 'Username updated', color: 'success' })
  } catch (error) {
    usernameError.value = message(error)
    toast.add({ title: 'Username not updated', description: message(error), color: 'error' })
  } finally {
    savingUsername.value = false
  }
}

/**
 * Changing a password ends every session server-side, including this one, so
 * the only honest next step is a fresh sign-in. (A stolen token cannot survive
 * the remediation.)
 */
async function savePassword() {
  if (savingPassword.value) return
  passwordError.value = ''
  savingPassword.value = true
  try {
    await api.request('auth/change-password', { method: 'POST', body: { current_password: currentPassword.value, new_password: newPassword.value } })
    currentPassword.value = ''
    newPassword.value = ''
    auth.clear()
    await navigateTo('/login?notice=password-changed')
  } catch (error) {
    passwordError.value = message(error)
    toast.add({ title: 'Password not updated', description: message(error), color: 'error' })
  } finally {
    savingPassword.value = false
  }
}

// ── MFA ──────────────────────────────────────────────────────────────────────
const mfaStatus = ref<MfaStatus | null>(null)
const loadingMfa = ref(true)
const mfaStatusError = ref('')
const mfaActionError = ref('')
const mfaPassword = ref('')
const mfaCode = ref('')
const pendingEnrollment = ref<MfaEnrollment | null>(null)
const busyMfa = ref(false)
// Newly regenerated codes, kept only until the page is left: the server stores
// hashes, so this is the one and only time they can be shown.
const regeneratedCodes = ref<string[]>([])
const busyCodes = ref(false)

async function loadMfaStatus() {
  loadingMfa.value = true
  mfaStatusError.value = ''
  try {
    mfaStatus.value = await api.request<MfaStatus>('auth/mfa/status')
  } catch (error) {
    mfaStatusError.value = message(error)
  } finally {
    loadingMfa.value = false
  }
}

/** Step 1 of enrolment: issue a secret (password re-verified server-side). */
async function startEnrollment() {
  if (busyMfa.value || busyCodes.value) return
  mfaActionError.value = ''
  busyMfa.value = true
  try {
    pendingEnrollment.value = await api.request<MfaEnrollment>('auth/mfa/reset', {
      method: 'POST',
      body: { current_password: mfaPassword.value }
    })
    mfaCode.value = ''
  } catch (error) {
    mfaActionError.value = message(error)
    toast.add({ title: 'Could not start setup', description: message(error), color: 'error' })
  } finally {
    busyMfa.value = false
  }
}

async function regenerateRecoveryCodes() {
  if (busyCodes.value || busyMfa.value) return
  mfaActionError.value = ''
  busyCodes.value = true
  try {
    const result = await api.request<MfaRecoveryCodes>('auth/mfa/recovery/regenerate', {
      method: 'POST',
      body: { current_password: mfaPassword.value }
    })
    regeneratedCodes.value = result.recovery_codes
    mfaPassword.value = ''
    await loadMfaStatus()
    toast.add({ title: 'New recovery codes issued', description: 'Every previous code no longer works.', color: 'success' })
  } catch (error) {
    mfaActionError.value = message(error)
    toast.add({ title: 'Could not issue new codes', description: message(error), color: 'error' })
  } finally {
    busyCodes.value = false
  }
}

/** Step 2: prove possession of the secret — only then is MFA enabled. */
async function confirmEnrollment() {
  if (busyMfa.value || busyCodes.value) return
  mfaActionError.value = ''
  busyMfa.value = true
  try {
    mfaStatus.value = await api.request<MfaStatus>('auth/mfa/confirm', {
      method: 'POST',
      body: { current_password: mfaPassword.value, code: mfaCode.value.trim() }
    })
    pendingEnrollment.value = null
    mfaPassword.value = ''
    mfaCode.value = ''
    toast.add({ title: 'Two-step verification enabled', description: 'Store your recovery codes: they are shown only while setting up.', color: 'success' })
  } catch (error) {
    mfaActionError.value = message(error)
    toast.add({ title: 'Code not accepted', description: message(error), color: 'error' })
  } finally {
    busyMfa.value = false
  }
}

async function disableMfa() {
  if (busyMfa.value || busyCodes.value) return
  mfaActionError.value = ''
  busyMfa.value = true
  try {
    await api.request('auth/mfa/disable', { method: 'POST', body: { current_password: mfaPassword.value } })
    mfaPassword.value = ''
    await loadMfaStatus()
    toast.add({ title: 'Authenticator removed', color: 'success' })
  } catch (error) {
    mfaActionError.value = message(error)
    toast.add({ title: 'Could not remove authenticator', description: message(error), color: 'error' })
  } finally {
    busyMfa.value = false
  }
}

// ── Signed-in devices ────────────────────────────────────────────────────────
const sessions = ref<SessionSummary[]>([])
const loadingSessions = ref(true)
const sessionsError = ref('')
const revokingSession = ref<number | 'all' | null>(null)

async function loadSessions() {
  loadingSessions.value = true
  sessionsError.value = ''
  try {
    sessions.value = await api.request<SessionSummary[]>('auth/sessions')
  } catch (error) {
    sessionsError.value = message(error)
  } finally {
    loadingSessions.value = false
  }
}

async function revokeSession(id: number) {
  if (revokingSession.value !== null) return
  revokingSession.value = id
  try {
    await api.request(`auth/sessions/${id}`, { method: 'DELETE' })
    await loadSessions()
    toast.add({ title: 'Device signed out', color: 'success' })
  } catch (error) {
    toast.add({ title: 'Could not sign that device out', description: message(error), color: 'error' })
  } finally {
    revokingSession.value = null
  }
}

async function revokeAllSessions() {
  if (revokingSession.value !== null) return
  revokingSession.value = 'all'
  try {
    await api.request('auth/sessions', { method: 'DELETE' })
    auth.clear()
    await navigateTo('/login')
  } catch (error) {
    toast.add({ title: 'Could not sign out everywhere', description: message(error), color: 'error' })
  } finally {
    revokingSession.value = null
  }
}

const deviceLabel = (session: SessionSummary) => session.user_agent?.split(')')[0]?.replace(/^Mozilla\/5\.0 \(/, '') || 'Unknown device'
const shortTime = (value: string | null | undefined) => value ? new Date(value).toLocaleString() : '—'

onMounted(async () => {
  await Promise.all([loadSessions(), loadMfaStatus()])
})
</script>

<template>
  <div
    class="people-page space-y-6"
    :class="isTechnicalAdmin ? 'max-w-6xl' : 'max-w-3xl'"
  >
    <div>
      <h1 class="mt-1 text-2xl font-semibold tracking-tight">
        {{ pageTitle }}
      </h1>
      <p class="mt-2 text-sm text-muted">
        {{ isTechnicalAdmin ? 'Manage the technical login and the operational controls available to this installation.' : 'Keep your Emploi account secure by updating your own password.' }}
      </p>
    </div>
    <UAlert
      v-if="passwordChangeRequired"
      color="warning"
      variant="soft"
      icon="i-lucide-key-round"
      title="Set a new password to continue"
      description="Your account is using a temporary password. Choose your own password below to finish activating it."
    />
    <UAlert
      v-if="isTechnicalAdmin"
      color="info"
      variant="soft"
      icon="i-lucide-shield-check"
      title="Technical account"
      description="This account is separate from employee records. Use it for system setup, integrations, access configuration and operational support."
    />

    <section class="people-card overflow-hidden">
      <div class="grid divide-y divide-[var(--people-border)] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div class="p-5">
          <UIcon
            name="i-lucide-key-round"
            class="size-5 text-primary"
          />
          <p class="mt-3 text-sm font-semibold">
            Password
          </p>
          <p class="mt-1 text-xs leading-5 text-muted">
            8+ characters, breach screened, and checked against your personal details.
          </p>
        </div>
        <div class="p-5">
          <UIcon
            :name="mfaStatus?.enabled ? 'i-lucide-shield-check' : 'i-lucide-shield-alert'"
            class="size-5 text-primary"
          />
          <p class="mt-3 text-sm font-semibold">
            {{ mfaStatus?.enabled ? 'MFA on every login' : 'MFA not enabled' }}
          </p>
          <p class="mt-1 text-xs leading-5 text-muted">
            {{ mfaStatus?.enabled ? 'A fresh password sign-in also requires your authenticator code.' : 'Turn it on below to protect new sign-ins.' }}
          </p>
        </div>
        <div class="p-5">
          <UIcon
            name="i-lucide-monitor-smartphone"
            class="size-5 text-primary"
          />
          <p class="mt-3 text-sm font-semibold">
            {{ sessions.length }} signed-in device{{ sessions.length === 1 ? '' : 's' }}
          </p>
          <p class="mt-1 text-xs leading-5 text-muted">
            Review and revoke access you do not recognize.
          </p>
        </div>
      </div>
    </section>

    <section
      v-if="isTechnicalAdmin"
      class="space-y-4"
    >
      <div>
        <h2 class="text-lg font-semibold">
          Workforce account administration
        </h2>
        <p class="mt-1 text-sm text-muted">
          Support workforce sign-in accounts without changing ERP-owned employee data.
        </p>
      </div>
      <TechnicalAccountAdministration />
    </section>

    <section
      v-if="isTechnicalAdmin"
      class="people-card space-y-5 p-5 sm:p-6"
    >
      <div>
        <h3 class="font-semibold">
          Username
        </h3><p class="mt-1 text-sm text-muted">
          This is the only identifier used for technical sign-in. Changing it requires your current password.
        </p>
      </div>
      <UFormField
        label="Username"
        name="username"
        hint="3–50 characters; letters, numbers, dots, dashes or underscores"
      >
        <UInput
          v-model="username"
          :aria-invalid="Boolean(usernameError)"
          aria-describedby="username-save-error"
          class="w-full max-w-md"
          icon="i-lucide-user-round-cog"
          placeholder="Enter username"
          autocomplete="username"
        />
      </UFormField>
      <UFormField
        label="Current password"
        name="username-password"
      >
        <AuthPasswordInput
          v-model="usernamePassword"
          :aria-invalid="Boolean(usernameError)"
          aria-describedby="username-save-error"
          class="w-full max-w-md"

          icon="i-lucide-lock-keyhole"
          autocomplete="current-password"
          placeholder="Confirm with your password"
        />
      </UFormField>
      <p
        v-if="usernameError"
        id="username-save-error"
        class="text-sm text-error"
        role="alert"
      >
        {{ usernameError }}
      </p>
      <UButton
        :loading="savingUsername"
        :disabled="savingUsername"
        icon="i-lucide-save"
        @click="saveUsername"
      >
        Save username
      </UButton>
    </section>

    <section class="people-card space-y-5 p-5 sm:p-6">
      <div>
        <h3 class="font-semibold">
          Password and sign-in
        </h3><p class="mt-1 text-sm text-muted">
          Choose a strong password for your own account. Changing it signs out every device and requires a fresh login.
        </p>
      </div>
      <div class="grid gap-5 sm:grid-cols-2">
        <div>
          <label
            for="current-password"
            class="text-sm font-medium"
          >Current password</label>
          <AuthPasswordInput
            id="current-password"
            v-model="currentPassword"
            aria-describedby="password-save-error"
            class="mt-2 w-full"

            icon="i-lucide-lock-keyhole"
            autocomplete="current-password"
          />
        </div>
        <div>
          <label
            for="new-password"
            class="text-sm font-medium"
          >New password</label>
          <AuthPasswordInput
            id="new-password"
            v-model="newPassword"
            class="mt-2 w-full"

            icon="i-lucide-key-round"
            autocomplete="new-password"
            aria-describedby="new-password-help password-save-error"
          />
          <p
            id="new-password-help"
            class="mt-2 text-xs leading-5 text-muted"
          >
            At least 8 characters. A passphrase is ideal. Avoid your name, email or username, and passwords known to have appeared in breaches.
          </p>
        </div>
      </div>
      <UAlert
        color="info"
        variant="soft"
        icon="i-lucide-info"
        description="Changing your password signs out every device, including this one. You will sign in again with the new password."
      />
      <p
        v-if="passwordError"
        id="password-save-error"
        class="text-sm text-error"
        role="alert"
      >
        {{ passwordError }}
      </p>
      <UButton
        :loading="savingPassword"
        :disabled="savingPassword"
        icon="i-lucide-key-round"
        @click="savePassword"
      >
        Change password
      </UButton>
    </section>

    <section class="people-card space-y-5 p-5 sm:p-6">
      <div>
        <h3 class="font-semibold">
          Require MFA on every login
        </h3>
        <p class="mt-1 text-sm text-muted">
          Turn this on to require an authenticator code after every new password sign-in. Existing sessions are not interrupted.
        </p>
      </div>
      <p
        v-if="loadingMfa"
        role="status"
        class="text-sm text-muted"
      >
        Loading verification status…
      </p>
      <UAlert
        v-if="mfaStatusError"
        color="error"
        title="Verification status could not be loaded"
        :description="mfaStatusError"
        :actions="[{ label: 'Retry', onClick: loadMfaStatus }]"
      />
      <UAlert
        v-if="mfaActionError"
        color="error"
        title="Verification change could not be completed"
        :description="mfaActionError"
        role="alert"
      />
      <UAlert
        v-if="mfaStatus"
        :color="mfaStatus?.enabled ? 'success' : 'warning'"
        variant="soft"
        :icon="mfaStatus?.enabled ? 'i-lucide-shield-check' : 'i-lucide-triangle-alert'"
        :title="mfaStatus?.replacement_pending
          ? 'Replacement awaiting confirmation'
          : (mfaStatus?.enabled ? 'Enabled' : 'Not set up')"
        :description="mfaStatus?.replacement_pending
          ? `Your current authenticator is still required and still works · ${mfaStatus.recovery_codes_remaining} recovery codes left`
          : (mfaStatus?.enabled
            ? `Enabled for every new login · enrolled ${shortTime(mfaStatus.enrolled_at)} · ${mfaStatus.recovery_codes_remaining} recovery codes left`
            : 'Anyone with the password alone can currently sign in to this account.')"
      />

      <template v-if="pendingEnrollment">
        <UAlert
          v-if="pendingEnrollment.replacing_existing"
          color="info"
          variant="soft"
          icon="i-lucide-info"
          title="Your current authenticator still works"
          description="It keeps signing you in, and your existing recovery codes stay valid, until you confirm the new one below."
        />
        <div class="space-y-3 rounded-xl border border-[var(--people-border)] p-4">
          <MfaQrCode
            :uri="pendingEnrollment.otpauth_uri"
            :secret="pendingEnrollment.secret"
          />
          <div v-if="pendingEnrollment.recovery_codes.length">
            <p class="text-xs font-medium uppercase tracking-wide text-muted">
              Recovery codes (shown once)
            </p>
            <div class="mt-2 grid gap-2 font-mono text-sm sm:grid-cols-2">
              <span
                v-for="recovery in pendingEnrollment.recovery_codes"
                :key="recovery"
              >{{ recovery }}</span>
            </div>
          </div>
        </div>
        <UFormField
          label="Code from the app"
          name="mfa-code"
          required
        >
          <UInput
            v-model="mfaCode"
            class="w-full max-w-xs"
            inputmode="numeric"
            autocomplete="one-time-code"
            placeholder="123456"
          />
        </UFormField>
        <div class="flex gap-3">
          <UButton
            :loading="busyMfa"
            :disabled="busyMfa || busyCodes || !mfaCode.trim()"
            icon="i-lucide-check"
            @click="confirmEnrollment"
          >
            Confirm and enable
          </UButton>
          <UButton
            variant="ghost"
            :disabled="busyMfa"
            @click="pendingEnrollment = null"
          >
            Cancel
          </UButton>
        </div>
      </template>

      <template v-else-if="mfaStatus && !loadingMfa">
        <UFormField
          label="Current password"
          name="mfa-password"
          required
        >
          <AuthPasswordInput
            v-model="mfaPassword"
            class="w-full max-w-md"

            icon="i-lucide-lock-keyhole"
            autocomplete="current-password"
            placeholder="Confirm with your password"
          />
        </UFormField>
        <div class="flex flex-wrap gap-3">
          <UButton
            :loading="busyMfa"
            :disabled="busyMfa || busyCodes || !mfaPassword"
            icon="i-lucide-shield-plus"
            @click="startEnrollment"
          >
            {{ mfaStatus?.enabled ? 'Replace authenticator' : 'Enable MFA for every login' }}
          </UButton>
          <UButton
            v-if="mfaStatus?.enabled"
            variant="soft"
            :loading="busyCodes"
            :disabled="busyCodes || busyMfa || !mfaPassword"
            icon="i-lucide-key-round"
            @click="regenerateRecoveryCodes"
          >
            Issue new recovery codes
          </UButton>
          <UButton
            v-if="mfaStatus?.enabled"
            color="error"
            variant="soft"
            :loading="busyMfa"
            :disabled="busyMfa || busyCodes || !mfaPassword"
            icon="i-lucide-shield-off"
            @click="disableMfa"
          >
            Turn off MFA
          </UButton>
        </div>

        <div
          v-if="regeneratedCodes.length"
          class="space-y-2 rounded-xl border border-[var(--people-border)] p-4"
        >
          <p class="text-xs font-medium uppercase tracking-wide text-muted">
            New recovery codes (shown once)
          </p>
          <div class="grid gap-2 font-mono text-sm sm:grid-cols-2">
            <span
              v-for="code in regeneratedCodes"
              :key="code"
            >{{ code }}</span>
          </div>
          <p class="text-xs text-muted">
            Save these now. Your previous codes no longer work. Each one signs you in once if you lose your device.
          </p>
          <UButton
            variant="ghost"
            size="sm"
            @click="regeneratedCodes = []"
          >
            I’ve saved them
          </UButton>
        </div>
      </template>
    </section>

    <section class="people-card space-y-4 p-5 sm:p-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="font-semibold">
            Signed-in devices
          </h3>
          <p class="mt-1 text-sm text-muted">
            Sessions currently able to act as you. Revoke anything you do not recognise.
          </p>
        </div>
        <UButton
          v-if="sessions.length > 1"
          color="error"
          variant="soft"
          size="sm"
          icon="i-lucide-log-out"
          :loading="revokingSession === 'all'"
          :disabled="revokingSession !== null || loadingSessions"
          @click="revokeAllSessions"
        >
          Sign out everywhere
        </UButton>
      </div>
      <p
        v-if="loadingSessions"
        role="status"
        class="text-sm text-muted"
      >
        Loading signed-in devices…
      </p>
      <UAlert
        v-if="sessionsError"
        color="error"
        title="Devices could not be loaded"
        :description="sessionsError"
        :actions="[{ label: 'Retry', onClick: loadSessions }]"
      />
      <ul class="divide-y divide-[var(--people-border)]">
        <li
          v-for="device in sessions"
          :key="device.id"
          class="flex flex-wrap items-center justify-between gap-3 py-3"
        >
          <div class="min-w-0">
            <p class="break-words text-sm font-medium">
              {{ deviceLabel(device) }}
              <UBadge
                v-if="device.is_current"
                size="sm"
                variant="soft"
                class="ml-2"
              >
                This device
              </UBadge>
            </p>
            <p class="mt-1 text-xs text-muted">
              Last used {{ shortTime(device.last_used_at || device.created_at) }} · {{ device.ip_address || 'unknown address' }}
            </p>
          </div>
          <UButton
            v-if="!device.is_current"
            size="sm"
            variant="ghost"
            color="error"
            :loading="revokingSession === device.id"
            :disabled="revokingSession !== null || loadingSessions"
            @click="revokeSession(device.id)"
          >
            Revoke
          </UButton>
        </li>
        <li
          v-if="!loadingSessions && !sessionsError && !sessions.length"
          class="py-3 text-sm text-muted"
        >
          No active sessions found.
        </li>
      </ul>
    </section>
  </div>
</template>
