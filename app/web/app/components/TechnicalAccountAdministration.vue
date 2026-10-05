<script setup lang="ts">
import type {
  TechnicalAccount,
  TechnicalAccountActionResponse,
  TemporaryPasswordResponse
} from '#shared/types/auth'
import type { PaginatedResponse } from '#shared/types/pagination'

type SupportAction = 'password' | 'sessions' | 'status' | 'mfa'

const api = useHrmsApi()
const toast = useToast()
const list = useListState({ sort_order: 'asc' }, 'accounts_')
const selected = ref<TechnicalAccount | null>(null)
const action = ref<SupportAction | null>(null)
const currentPassword = ref('')
const temporaryPassword = ref('')
const busy = ref(false)
const actionError = ref('')
const sortPanelId = `account-sort-${useId()}`
const showSort = ref(false)
const searchInput = ref(list.search.value)

const submittedSearch = computed(() => String(list.query.value.search || ''))

watch(() => list.search.value, (value) => {
  if (value !== searchInput.value) searchInput.value = value
})

const { data: rawData, pending, error, refresh } = await useAsyncData(
  'technical-account-directory',
  (_app, { signal }) => api.request<PaginatedResponse<TechnicalAccount>>('users/admin/accounts', {
    signal,
    query: list.query.value
  }),
  { watch: [list.query] }
)
const data = useRetainedData(rawData)
watch(searchInput, (value) => {
  if (!value && submittedSearch.value) void list.update({ search: '' })
})
const directoryError = computed(() => {
  const requestError = error.value as { data?: { detail?: string, statusMessage?: string }, message?: string } | null
  return requestError?.data?.detail || requestError?.data?.statusMessage || requestError?.message || 'The login-account list could not be loaded.'
})

const displayName = (account: TechnicalAccount) => [account.first_name, account.last_name].filter(Boolean).join(' ') || account.username
const roleLabel = (value?: string | null) => value?.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()) || 'Employee'
const dialogTitle = computed(() => {
  if (action.value === 'password') return 'Generate temporary password'
  if (action.value === 'sessions') return 'Sign out every device'
  if (action.value === 'mfa') return 'Reset authenticator'
  return selected.value?.is_active ? 'Suspend login account' : 'Reactivate login account'
})
const dialogDescription = computed(() => {
  if (action.value === 'password') return 'A one-time password will be shown once. The user must replace it after signing in.'
  if (action.value === 'sessions') return 'Every refresh session for this account will be revoked immediately.'
  if (action.value === 'mfa') return 'The enrolled authenticator and recovery codes will be removed, and all devices will be signed out.'
  return selected.value?.is_active
    ? 'The account will be unable to sign in and every device will be signed out.'
    : 'The account will be allowed to sign in again.'
})

function start(account: TechnicalAccount, nextAction: SupportAction) {
  selected.value = account
  action.value = nextAction
  currentPassword.value = ''
  temporaryPassword.value = ''
  actionError.value = ''
}

function close() {
  selected.value = null
  action.value = null
  currentPassword.value = ''
  temporaryPassword.value = ''
  actionError.value = ''
}

async function submit() {
  if (busy.value || !selected.value || !action.value || !currentPassword.value) return
  actionError.value = ''
  busy.value = true
  const account = selected.value
  try {
    if (action.value === 'password') {
      const result = await api.request<TemporaryPasswordResponse>(`users/admin/accounts/${account.id}/temporary-password`, {
        method: 'POST', body: { current_password: currentPassword.value }
      })
      temporaryPassword.value = result.temporary_password
      currentPassword.value = ''
      toast.add({ title: 'Temporary password generated', description: 'Copy it now; it will not be shown again.', color: 'success' })
    } else if (action.value === 'sessions') {
      const result = await api.request<TechnicalAccountActionResponse>(`users/admin/accounts/${account.id}/revoke-sessions`, {
        method: 'POST', body: { current_password: currentPassword.value }
      })
      toast.add({ title: 'Devices signed out', description: `${result.revoked_sessions} active session(s) revoked.`, color: 'success' })
      close()
    } else if (action.value === 'mfa') {
      await api.request(`users/admin/accounts/${account.id}/mfa-reset`, {
        method: 'POST', body: { current_password: currentPassword.value }
      })
      toast.add({ title: 'Authenticator reset', description: 'The user can enroll a new authenticator after signing in.', color: 'success' })
      close()
    } else {
      await api.request(`users/admin/accounts/${account.id}/status`, {
        method: 'PATCH', body: { current_password: currentPassword.value, is_active: !account.is_active }
      })
      toast.add({ title: account.is_active ? 'Account suspended' : 'Account reactivated', color: 'success' })
      close()
    }
    await refresh()
  } catch (requestError) {
    const description = (requestError as { data?: { detail?: string, statusMessage?: string } }).data?.detail
      || (requestError as { data?: { statusMessage?: string } }).data?.statusMessage
      || 'The account action could not be completed.'
    actionError.value = description
    toast.add({ title: 'Action failed', description, color: 'error' })
  } finally {
    busy.value = false
  }
}

async function copyTemporaryPassword() {
  if (!temporaryPassword.value) return
  try {
    await navigator.clipboard.writeText(temporaryPassword.value)
    toast.add({ title: 'Password copied', color: 'success' })
  } catch {
    toast.add({
      title: 'Copy unavailable',
      description: 'Select and copy the temporary password manually.',
      color: 'warning'
    })
  }
}

function runAccountSearch() {
  if (pending.value) return
  const search = searchInput.value.trim()
  searchInput.value = search
  void list.update({ search })
}

function clearAccountFilters() {
  searchInput.value = ''
  list.clear()
}
</script>

<template>
  <section class="people-card space-y-5 p-5 sm:p-6">
    <div class="flex items-start gap-3">
      <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-[var(--people-blue)] text-primary">
        <UIcon
          name="i-lucide-users-round"
          class="size-5"
        />
      </span>
      <div class="min-w-0">
        <h3 class="mt-0.5 text-lg font-semibold">
          Login accounts
        </h3>
        <p class="mt-1 max-w-3xl text-sm leading-6 text-muted">
          Find an employee account, then reset its password, sign out its devices, reset MFA, or suspend login access. Each action asks for your Super Admin password and is audited.
        </p>
      </div>
    </div>

    <form
      class="rounded-xl border border-[var(--people-border)] bg-[var(--people-canvas)]/45 p-3 sm:p-4"
      aria-label="Find an account"
      @submit.prevent="runAccountSearch"
    >
      <div class="flex flex-col gap-3">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-end">
          <UFormField
            label="Find an account"
            description="Search by name, username, email, mobile, or employee code"
            class="min-w-0 flex-1"
          >
            <SearchInput
              v-model="searchInput"
              placeholder="Enter an employee identifier"
              autocomplete="off"
              class="w-full"
            />
          </UFormField>
          <div class="flex flex-wrap gap-2 sm:shrink-0 sm:pb-px">
            <UButton
              type="submit"
              icon="i-lucide-search"
              :loading="pending"
              :disabled="pending"
            >
              Search
            </UButton>
            <UButton
              type="button"
              color="neutral"
              variant="outline"
              :icon="showSort ? 'i-lucide-chevron-up' : 'i-lucide-arrow-up-down'"
              :aria-expanded="showSort"
              :aria-controls="sortPanelId"
              @click="showSort = !showSort"
            >
              {{ showSort ? 'Hide sort' : 'Sort' }}
            </UButton>
            <UButton
              v-if="list.active.value || searchInput"
              type="button"
              color="neutral"
              variant="ghost"
              icon="i-lucide-x"
              @click="clearAccountFilters"
            >
              Reset filters
            </UButton>
          </div>
        </div>

        <div
          v-if="showSort"
          :id="sortPanelId"
          class="grid gap-3 border-t border-[var(--people-border)] pt-3 sm:grid-cols-2"
        >
          <UFormField label="Sort by">
            <USelect
              v-model="list.sortBy.value"
              :items="[
                { label: 'Default order', value: '' },
                { label: 'Username', value: 'username' },
                { label: 'Email', value: 'email' },
                { label: 'Created', value: 'created_at' },
                { label: 'Account status', value: 'is_active' }
              ]"
              aria-label="Sort accounts by"
              class="w-full"
            />
          </UFormField>
          <UFormField label="Order">
            <USelect
              v-model="list.sortOrder.value"
              :items="[{ label: 'Ascending', value: 'asc' }, { label: 'Descending', value: 'desc' }]"
              aria-label="Account sort order"
              class="w-full"
            />
          </UFormField>
        </div>
      </div>
      <p
        v-if="submittedSearch && !pending"
        class="mt-3 text-xs text-muted"
        role="status"
      >
        Showing results for “{{ submittedSearch }}”
      </p>
    </form>

    <DataFeedback
      :pending="pending"
      :error="error"
      :has-data="Boolean(data)"
    />
    <div
      v-if="pending && !data"
      class="space-y-3"
      aria-hidden="true"
    >
      <USkeleton
        v-for="row in 4"
        :key="row"
        class="h-16 w-full"
      />
    </div>
    <div
      v-if="error"
      class="rounded-xl border border-[var(--people-border)] bg-[var(--people-rose)] p-5"
      role="alert"
    >
      <div class="flex items-start gap-3">
        <UIcon
          name="i-lucide-circle-alert"
          class="mt-0.5 size-5 shrink-0 text-error"
        />
        <div class="min-w-0 flex-1">
          <h4 class="font-semibold">
            Account directory unavailable
          </h4>
          <p class="mt-1 text-sm text-muted">
            {{ directoryError }}
          </p>
          <UButton
            class="mt-3"
            color="neutral"
            variant="outline"
            size="sm"
            icon="i-lucide-refresh-cw"
            @click="() => refresh()"
          >
            Retry
          </UButton>
        </div>
      </div>
    </div>
    <div
      v-if="!pending && !error && !data?.items.length"
      class="rounded-xl border border-dashed border-[var(--people-border)] px-5 py-10 text-center"
      role="status"
    >
      <span class="mx-auto grid size-11 place-items-center rounded-xl bg-[var(--people-blue)] text-primary">
        <UIcon
          name="i-lucide-user-search"
          class="size-5"
        />
      </span>
      <h4 class="mt-3 font-semibold">
        {{ submittedSearch ? `No account matches “${submittedSearch}”` : 'No workforce accounts available' }}
      </h4>
      <p class="mx-auto mt-1 max-w-md text-sm text-muted">
        {{ submittedSearch ? 'Check the spelling or search by another identifier.' : 'Workforce login accounts will appear here after they are provisioned.' }}
      </p>
      <UButton
        v-if="submittedSearch"
        class="mt-4"
        color="neutral"
        variant="outline"
        icon="i-lucide-x"
        @click="clearAccountFilters"
      >
        Clear search
      </UButton>
    </div>

    <template v-if="data?.items.length">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-sm font-semibold">
          {{ data.total }} {{ data.total === 1 ? 'account' : 'accounts' }}
        </p>
        <p class="text-xs text-muted">
          Select a support action beside the employee
        </p>
      </div>

      <div class="hidden overflow-x-auto lg:block">
        <table class="w-full min-w-[900px] text-left text-sm">
          <thead class="border-b border-[var(--people-border)] text-xs uppercase tracking-wide text-muted">
            <tr>
              <th class="px-3 py-3">
                Account
              </th><th class="px-3 py-3">
                Role
              </th><th class="px-3 py-3">
                Security
              </th><th class="px-3 py-3 text-right">
                Support actions
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-[var(--people-border)]">
            <tr
              v-for="account in data.items"
              :key="account.id"
            >
              <td class="px-3 py-4">
                <p class="font-semibold">
                  {{ displayName(account) }}
                </p><p class="mt-1 text-xs text-muted">
                  {{ account.username }} · {{ account.email }}
                </p><p
                  v-if="account.employee_code"
                  class="mt-1 text-xs text-muted"
                >
                  {{ account.employee_code }}
                </p>
              </td>
              <td class="px-3 py-4">
                {{ roleLabel(account.employee_role) }}
              </td>
              <td class="px-3 py-4">
                <div class="flex flex-wrap gap-2">
                  <UBadge
                    :color="account.is_active ? 'success' : 'error'"
                    variant="soft"
                  >
                    {{ account.is_active ? 'Active' : 'Suspended' }}
                  </UBadge><UBadge
                    :color="account.mfa_enabled ? 'success' : 'neutral'"
                    variant="soft"
                  >
                    {{ account.mfa_enabled ? 'MFA' : 'No MFA' }}
                  </UBadge><UBadge
                    v-if="account.must_change_password"
                    color="warning"
                    variant="soft"
                  >
                    Password change due
                  </UBadge>
                </div>
              </td>
              <td class="px-3 py-4">
                <div class="flex justify-end gap-1">
                  <UButton
                    size="sm"
                    variant="ghost"
                    icon="i-lucide-key-round"
                    @click="start(account, 'password')"
                  >
                    Reset password
                  </UButton><UButton
                    size="sm"
                    variant="ghost"
                    icon="i-lucide-log-out"
                    @click="start(account, 'sessions')"
                  >
                    Sign out
                  </UButton><UButton
                    v-if="account.mfa_enabled"
                    size="sm"
                    variant="ghost"
                    icon="i-lucide-shield-off"
                    @click="start(account, 'mfa')"
                  >
                    MFA
                  </UButton><UButton
                    size="sm"
                    :color="account.is_active ? 'error' : 'success'"
                    variant="soft"
                    @click="start(account, 'status')"
                  >
                    {{ account.is_active ? 'Suspend' : 'Reactivate' }}
                  </UButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="grid gap-3 lg:hidden">
        <article
          v-for="account in data.items"
          :key="account.id"
          class="rounded-xl border border-[var(--people-border)] p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="font-semibold">
                {{ displayName(account) }}
              </p><p class="mt-1 text-xs text-muted">
                {{ account.username }} · {{ account.employee_code || 'No employee code' }}
              </p>
            </div><UBadge
              :color="account.is_active ? 'success' : 'error'"
              variant="soft"
            >
              {{ account.is_active ? 'Active' : 'Suspended' }}
            </UBadge>
          </div>
          <p class="mt-3 break-all text-sm text-muted">
            {{ account.email }}
          </p>
          <div class="mt-3 flex flex-wrap gap-2">
            <UBadge
              color="neutral"
              variant="soft"
            >
              {{ roleLabel(account.employee_role) }}
            </UBadge><UBadge
              :color="account.mfa_enabled ? 'success' : 'neutral'"
              variant="soft"
            >
              {{ account.mfa_enabled ? 'MFA enabled' : 'No MFA' }}
            </UBadge><UBadge
              v-if="account.must_change_password"
              color="warning"
              variant="soft"
            >
              Password change due
            </UBadge>
          </div>
          <div class="mt-4 grid grid-cols-2 gap-2">
            <UButton
              variant="soft"
              icon="i-lucide-key-round"
              @click="start(account, 'password')"
            >
              Reset password
            </UButton><UButton
              variant="soft"
              icon="i-lucide-log-out"
              @click="start(account, 'sessions')"
            >
              Sign out devices
            </UButton><UButton
              v-if="account.mfa_enabled"
              variant="soft"
              icon="i-lucide-shield-off"
              @click="start(account, 'mfa')"
            >
              Reset MFA
            </UButton><UButton
              :color="account.is_active ? 'error' : 'success'"
              variant="soft"
              @click="start(account, 'status')"
            >
              {{ account.is_active ? 'Suspend' : 'Reactivate' }}
            </UButton>
          </div>
        </article>
      </div>

      <ListPagination
        v-model:page="list.page.value"
        v-model:page-size="list.pageSize.value"
        :total="data.total"
        :total-pages="data.total_pages"
        :loading="pending"
        label="accounts"
      />
    </template>

    <UModal
      :open="Boolean(selected && action)"
      :title="dialogTitle"
      :description="dialogDescription"
      :dismissible="!busy"
      @update:open="value => { if (!value) close() }"
    >
      <template #body>
        <section class="w-full space-y-5">
          <div>
            <p class="mt-2 text-sm leading-6 text-muted">
              {{ selected ? displayName(selected) : '' }} · {{ selected?.username }}
            </p>
          </div>
          <div
            v-if="temporaryPassword"
            class="rounded-xl border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-950/30"
          >
            <p class="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
              Shown once
            </p><code class="mt-2 block break-all text-base font-semibold">{{ temporaryPassword }}</code><UButton
              class="mt-3"
              size="sm"
              icon="i-lucide-copy"
              @click="copyTemporaryPassword"
            >
              Copy password
            </UButton>
          </div>
          <UFormField
            v-else
            label="Your current Super Admin password"
            required
          >
            <AuthPasswordInput
              v-model="currentPassword"
              autocomplete="current-password"
              class="w-full"
              autofocus
            />
          </UFormField>
          <UAlert
            v-if="actionError"
            color="error"
            title="Action could not be completed"
            :description="actionError"
            role="alert"
          />
          <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <UButton
              color="neutral"
              variant="soft"
              :disabled="busy"
              @click="close"
            >
              {{ temporaryPassword ? 'Done' : 'Cancel' }}
            </UButton><UButton
              v-if="!temporaryPassword"
              :color="action === 'status' && selected?.is_active ? 'error' : 'primary'"
              :loading="busy"
              :disabled="busy || !currentPassword"
              @click="submit"
            >
              Confirm action
            </UButton>
          </div>
        </section>
      </template>
    </UModal>
  </section>
</template>
