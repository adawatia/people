<script setup lang="ts">
const auth = useAuth()
const api = useHrmsApi()
const toast = useToast()
const isTechnicalAdmin = computed(() => Boolean(auth.user.value?.is_superuser))
const pageTitle = computed(() => isTechnicalAdmin.value ? 'System administration' : 'Security settings')
useSeoMeta({ title: () => pageTitle.value })
const username = ref(auth.user.value?.username || '')
const currentPassword = ref('')
const newPassword = ref('')
const savingUsername = ref(false)
const savingPassword = ref(false)
const message = (error: unknown) => (error as { data?: { detail?: string, statusMessage?: string } }).data?.detail || (error as { data?: { statusMessage?: string } }).data?.statusMessage || 'Could not save the change.'

async function saveUsername() {
  savingUsername.value = true
  try {
    const result = await api.request<{ username: string }>('auth/super-admin/username', { method: 'PATCH', body: { username: username.value.trim() } })
    if (auth.user.value) auth.user.value.username = result.username
    toast.add({ title: 'Username updated', color: 'success' })
  } catch (error) { toast.add({ title: 'Username not updated', description: message(error), color: 'error' }) } finally { savingUsername.value = false }
}
async function savePassword() {
  savingPassword.value = true
  try {
    await api.request('auth/change-password', { method: 'POST', body: { current_password: currentPassword.value, new_password: newPassword.value } })
    currentPassword.value = ''; newPassword.value = ''
    toast.add({ title: 'Password updated', description: 'Use the new password next time you sign in.', color: 'success' })
  } catch (error) { toast.add({ title: 'Password not updated', description: message(error), color: 'error' }) } finally { savingPassword.value = false }
}
</script>

<template>
  <div class="max-w-3xl space-y-6">
    <div>
      <p class="text-sm font-medium text-primary">{{ isTechnicalAdmin ? 'Technical access' : 'Account security' }}</p>
      <h2 class="mt-1 text-2xl font-semibold tracking-tight">{{ pageTitle }}</h2>
      <p class="mt-2 text-sm text-muted">
        {{ isTechnicalAdmin ? 'Manage the technical login and the operational controls available to this installation.' : 'Keep your People account secure by updating your own password.' }}
      </p>
    </div>
    <UAlert v-if="isTechnicalAdmin" color="info" variant="soft" icon="i-lucide-shield-check" title="Technical account" description="This account is separate from employee records. Use it for system setup, integrations, access configuration and operational support." />
    <section v-if="isTechnicalAdmin" class="people-card space-y-5 p-5 sm:p-6">
      <div><h3 class="font-semibold">Username</h3><p class="mt-1 text-sm text-muted">This is the only identifier used for technical sign-in.</p></div>
      <UFormField label="Username" name="username" hint="3–50 characters; letters, numbers, dots, dashes or underscores">
        <UInput v-model="username" class="w-full max-w-md" icon="i-lucide-user-round-cog" placeholder="Enter username" autocomplete="username" />
      </UFormField>
      <UButton :loading="savingUsername" icon="i-lucide-save" @click="saveUsername">Save username</UButton>
    </section>
    <section class="people-card space-y-5 p-5 sm:p-6">
      <div><h3 class="font-semibold">Password</h3><p class="mt-1 text-sm text-muted">Choose a strong password for your own account. Your current password is required.</p></div>
      <div class="grid gap-5 sm:grid-cols-2">
        <div>
          <label for="current-password" class="text-sm font-medium">Current password</label>
          <UInput id="current-password" v-model="currentPassword" class="mt-2 w-full" type="password" icon="i-lucide-lock-keyhole" autocomplete="current-password" />
        </div>
        <div>
          <label for="new-password" class="text-sm font-medium">New password</label>
          <UInput id="new-password" v-model="newPassword" class="mt-2 w-full" type="password" icon="i-lucide-key-round" autocomplete="new-password" aria-describedby="new-password-help" />
          <p id="new-password-help" class="mt-2 text-xs leading-5 text-muted">
            At least 12 characters with upper, lower, number and symbol.
          </p>
        </div>
      </div>
      <UButton :loading="savingPassword" icon="i-lucide-key-round" @click="savePassword">Change password</UButton>
    </section>
  </div>
</template>
