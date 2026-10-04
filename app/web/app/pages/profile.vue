<script setup lang="ts">
import type { CurrentUser } from '#shared/types/auth'

useSeoMeta({ title: 'Profile' })
const auth = useAuth()
const api = useHrmsApi()
const { data: rawEmployee, pending, error, refresh } = useLazyAsyncData('profile-employee', () => auth.user.value?.employee_id ? api.request<Record<string, unknown>>(`employees/${auth.user.value.employee_id}`) : Promise.resolve(null), { watch: [() => auth.user.value?.employee_id] })
const employee = useRetainedData(rawEmployee)

const user = computed(() => auth.user.value as CurrentUser | null)
// Label from the business role + scope, so unit HR and organization HR are
// distinguishable. Display only — authorization always comes from the API.
const roleLabel = computed(() => {
  switch (user.value?.business_role) {
    case 'ORGANIZATION_OWNER': return 'Organization Owner'
    case 'HR_ADMIN': return user.value.scope_type === 'ORGANIZATION' ? 'HR Admin (Organization)' : 'HR Admin (Unit)'
    case 'DEPARTMENT_MANAGER': return 'Department Manager'
    default: return user.value?.is_superuser || user.value?.role === 'SUPER_ADMIN' ? 'Super Admin' : 'Employee'
  }
})
const details = computed(() => [
  { label: 'Full name', value: employee.value?.full_name || [user.value?.first_name, user.value?.last_name].filter(Boolean).join(' ') || user.value?.username },
  { label: 'Employee code', value: employee.value?.employee_code || user.value?.employee_code },
  { label: 'Mobile number', value: employee.value?.phone_number || user.value?.mobile_number },
  { label: 'Official email', value: employee.value?.official_email || user.value?.email },
  { label: 'Role', value: roleLabel.value },
  { label: 'Department', value: employee.value?.department_name },
  { label: 'Unit', value: employee.value?.unit_name },
  { label: 'Designation', value: employee.value?.designation_name || employee.value?.designation }
])
</script>

<template>
  <div class="people-page mx-auto max-w-4xl">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          My profile
        </h1>
        <p class="mt-2 text-sm text-muted">
          View your personal and employment information.
        </p>
      </div>
      <UButton
        to="/settings"
        color="neutral"
        variant="soft"
        icon="i-lucide-lock-keyhole"
      >
        Security settings
      </UButton>
    </div>
    <DataFeedback
      :pending="pending"
      :error="error"
      :has-data="Boolean(employee)"
    />
    <UAlert
      v-if="error"
      title="Employment details could not be loaded"
      color="error"
      :actions="[{ label: 'Retry profile', onClick: () => refresh() }]"
    />
    <section class="people-card mt-7 overflow-hidden">
      <div class="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:p-7">
        <UAvatar
          :text="auth.initials.value"
          size="3xl"
          class="shrink-0 ring-4 ring-[var(--people-forest)]"
        />
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-xl font-semibold">
            {{ auth.displayName.value }}
            </h2>
            <UBadge color="success" variant="soft" icon="i-lucide-circle-check">
              Active account
            </UBadge>
          </div>
          <p class="mt-1 text-sm text-muted">
            {{ roleLabel }} · {{ user?.username }}
          </p>
          <p class="mt-4 max-w-xl text-sm leading-6 text-muted">
            Your employment record is synchronized from ERP. Contact your HR team if a work or contact detail is incorrect.
          </p>
        </div>
      </div>
      <div class="grid border-t border-[var(--people-border)] sm:grid-cols-3">
        <div class="p-5 sm:border-r sm:border-[var(--people-border)]">
          <p class="text-xs font-medium text-muted">Account role</p>
          <p class="mt-1 text-sm font-semibold">{{ roleLabel }}</p>
        </div>
        <div class="border-t border-[var(--people-border)] p-5 sm:border-l-0 sm:border-t-0 sm:border-r sm:border-[var(--people-border)]">
          <p class="text-xs font-medium text-muted">Employee code</p>
          <p class="mt-1 text-sm font-semibold">{{ employee?.employee_code || user?.employee_code || 'Not available' }}</p>
        </div>
        <div class="border-t border-[var(--people-border)] p-5 sm:border-l-0 sm:border-t-0">
          <p class="text-xs font-medium text-muted">Access scope</p>
          <p class="mt-1 text-sm font-semibold">{{ user?.scope_type?.toLowerCase() || 'Self' }}</p>
        </div>
      </div>
    </section>
    <section class="people-card mt-6 overflow-hidden">
      <div class="border-b border-[var(--people-border)] p-5 sm:px-6">
        <h2 class="font-semibold">Personal and employment details</h2>
        <p class="mt-1 text-sm text-muted">Read-only details supplied by your People and ERP records.</p>
      </div>
      <div
        v-if="pending && !employee"
        class="grid gap-4 p-5 sm:grid-cols-2"
      >
        <USkeleton
          v-for="item in 8"
          :key="item"
          class="h-12"
        />
      </div>
      <div
        v-else
        class="grid gap-px bg-[var(--people-border)] sm:grid-cols-2"
      >
        <div
          v-for="item in details"
          :key="item.label"
          class="bg-default p-5"
        >
          <p class="text-xs font-medium text-muted">
            {{ item.label }}
          </p>
          <p class="mt-1 break-words text-sm font-semibold">
            {{ item.value || 'Not available' }}
          </p>
        </div>
      </div>
    </section>
  </div>
</template>
