<script setup lang="ts">
import type { CurrentUser } from '#shared/types/auth'

useSeoMeta({ title: 'Profile' })
const auth = useAuth()
const api = useHrmsApi()
const employee = ref<Record<string, unknown> | null>(null)
const pending = ref(false)

if (auth.user.value?.employee_id) {
  pending.value = true
  try {
    employee.value = await api.request<Record<string, unknown>>(`employees/${auth.user.value.employee_id}`)
  } finally {
    pending.value = false
  }
}

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
  <div class="mx-auto max-w-4xl">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Account
        </p>
        <h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          My profile
        </h2>
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
    <UCard class="relative mt-7 overflow-hidden">
      <img src="/branding/dat-labs-symbol-dark.svg" alt="" aria-hidden="true" class="pointer-events-none absolute -right-5 -top-8 size-36 opacity-[0.035] dark:hidden">
      <img src="/branding/dat-labs-symbol-light.svg" alt="" aria-hidden="true" class="pointer-events-none absolute -right-5 -top-8 hidden size-36 opacity-[0.06] dark:block">
      <div class="relative flex flex-col gap-5 sm:flex-row sm:items-center">
        <UAvatar
          :text="auth.initials.value"
          size="3xl"
        />
        <div class="min-w-0">
          <h3 class="text-xl font-semibold">
            {{ auth.displayName.value }}
          </h3>
          <p class="mt-1 text-sm text-muted">
            {{ roleLabel }} · {{ user?.username }}
          </p>
          <UBadge
            class="mt-3"
            color="success"
            variant="soft"
          >
            Active account
          </UBadge>
        </div>
      </div>
    </UCard>
    <UCard
      class="mt-6"
      :ui="{ body: 'p-0 sm:p-0' }"
    >
      <template #header>
        <h3 class="font-semibold">
          Personal and employment details
        </h3>
      </template>
      <div
        v-if="pending"
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
    </UCard>
  </div>
</template>
