<script setup lang="ts">
/* eslint-disable @stylistic/max-statements-per-line */
/* eslint-disable better-tailwindcss/no-unknown-classes */
import type { Department, Designation, Organization, Unit } from '#shared/types/organization'

type Tab = 'units' | 'departments' | 'designations'
useSeoMeta({ title: 'Organization' })
const api = useHrmsApi()
const toast = useToast()
const activeTab = ref<Tab>('units')
const createOpen = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ name: '', code: '', city: '', description: '', unit_id: undefined as number | undefined })
const { data, pending, error, refresh } = await useAsyncData('organization-workspace', async () => {
  const [organization, units, departments, designations] = await Promise.all([api.request<Organization>('org/organization'), api.request<Unit[]>('org/units'), api.request<Department[]>('org/departments'), api.request<Designation[]>('designations/')])
  return { organization, units, departments, designations }
})
const totalActive = computed(() => ({ units: data.value?.units.filter(item => item.is_active).length || 0, departments: data.value?.departments.filter(item => item.is_active).length || 0, designations: data.value?.designations.filter(item => item.is_active).length || 0 }))
function unitName(id: number) {
  return data.value?.units.find(item => item.id === id)?.name || `Unit #${id}`
}
function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', code: '', city: '', description: '', unit_id: data.value?.units[0]?.id })
  createOpen.value = true
}
function openEdit(item: Unit | Department | Designation) {
  editingId.value = item.id
  Object.assign(form, { name: item.name, code: item.code || '', city: 'city' in item ? item.city || '' : '', description: 'description' in item ? item.description || '' : '', unit_id: 'unit_id' in item ? item.unit_id : data.value?.units[0]?.id })
  createOpen.value = true
}
function itemPath(itemId: number) {
  if (activeTab.value === 'units') return `org/units/${itemId}`
  if (activeTab.value === 'departments') return `org/departments/${itemId}`
  return `designations/${itemId}`
}
async function saveItem() {
  if (!form.name.trim()) return
  saving.value = true
  try {
    const body = activeTab.value === 'units' ? { name: form.name.trim(), code: form.code.trim() || null, city: form.city.trim() || null } : activeTab.value === 'departments' ? { name: form.name.trim(), code: form.code.trim() || null, unit_id: form.unit_id } : { name: form.name.trim(), code: form.code.trim() || null, description: form.description.trim() || null }
    const path = editingId.value ? itemPath(editingId.value) : activeTab.value === 'units' ? 'org/units' : activeTab.value === 'departments' ? 'org/departments' : 'designations/'
    await api.request(path, { method: editingId.value ? 'PATCH' : 'POST', body })
    createOpen.value = false
    toast.add({ title: `${activeTab.value.slice(0, -1)} ${editingId.value ? 'updated' : 'created'}`, color: 'success', icon: 'i-lucide-circle-check' })
    await refresh()
  } catch (saveError) {
    const candidate = saveError as { data?: { detail?: string, statusMessage?: string } }
    toast.add({ title: 'Could not save item', description: candidate.data?.detail || candidate.data?.statusMessage, color: 'error' })
  } finally { saving.value = false }
}
async function toggleItem(item: Unit | Department | Designation) {
  try { await api.request(itemPath(item.id), { method: 'PATCH', body: { is_active: !item.is_active } }); toast.add({ title: `${item.name} ${item.is_active ? 'disabled' : 'enabled'}`, color: 'success' }); await refresh() } catch (toggleError) { const candidate = toggleError as { data?: { detail?: string, statusMessage?: string } }; toast.add({ title: 'Could not change status', description: candidate.data?.detail || candidate.data?.statusMessage, color: 'error' }) }
}
async function deleteItem(item: Unit | Department | Designation) {
  if (!confirm(`Delete ${item.name}? This cannot be undone.`)) return
  try { await api.request(itemPath(item.id), { method: 'DELETE' }); toast.add({ title: `${item.name} deleted`, color: 'success' }); await refresh() } catch (deleteError) { const candidate = deleteError as { data?: { detail?: string, statusMessage?: string } }; toast.add({ title: 'Could not delete item', description: candidate.data?.detail || candidate.data?.statusMessage, color: 'error' }) }
}
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Company structure
        </p><h2 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Organization
        </h2><p class="mt-2 text-sm text-muted">
          Organization structure is synchronized from ERP and shown here as read-only data.
        </p>
      </div><UBadge color="info" variant="soft" icon="i-lucide-database">Managed by ERP</UBadge>
    </div>
    <section class="mt-7 grid gap-4 sm:grid-cols-3">
      <article
        v-for="metric in [{ key: 'units', label: 'Active units', icon: 'i-lucide-building-2', value: totalActive.units, bg: 'var(--people-blue)' }, { key: 'departments', label: 'Departments', icon: 'i-lucide-network', value: totalActive.departments, bg: 'var(--people-mint)' }, { key: 'designations', label: 'Designations', icon: 'i-lucide-badge', value: totalActive.designations, bg: 'var(--people-lavender)' }]"
        :key="metric.key"
        class="people-card p-5"
      >
        <div class="flex items-center justify-between">
          <p class="text-sm text-muted">
            {{ metric.label }}
          </p><span
            class="grid size-10 place-items-center rounded-xl"
            :style="{ background: metric.bg }"
          ><UIcon
            :name="metric.icon"
            class="size-5"
          /></span>
        </div><p class="mt-5 text-3xl font-semibold tabular-nums">
          {{ pending ? '—' : metric.value }}
        </p>
      </article>
    </section>
    <div class="mt-7 flex gap-2 overflow-x-auto border-b border-[var(--people-border)]">
      <button
        v-for="tab in [{ key: 'units', label: 'Units', icon: 'i-lucide-building-2' }, { key: 'departments', label: 'Departments', icon: 'i-lucide-network' }, { key: 'designations', label: 'Designations', icon: 'i-lucide-badge' }]"
        :key="tab.key"
        class="flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold"
        :class="activeTab === tab.key ? 'border-primary text-primary' : 'border-transparent text-muted'"
        @click="activeTab = tab.key as Tab"
      >
        <UIcon :name="tab.icon" />{{ tab.label }}
      </button>
    </div>
    <UAlert
      v-if="error"
      class="mt-5"
      color="warning"
      variant="soft"
      icon="i-lucide-coffee"
      title="Organization details are taking a short break"
      description="We couldn’t refresh these details right now. Please try again in a moment."
      :actions="[{ label: 'Refresh details', onClick: () => refresh() }]"
    />
    <div
      v-else-if="pending"
      class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <USkeleton
        v-for="i in 6"
        :key="i"
        class="h-40 rounded-2xl"
      />
    </div>
    <section
      v-else-if="activeTab === 'units'"
      class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <article
        v-for="item in data?.units"
        :key="item.id"
        class="people-card p-5"
      >
        <div class="flex items-start justify-between">
          <span class="grid size-11 place-items-center rounded-xl bg-[var(--people-blue)]"><UIcon
            name="i-lucide-building-2"
            class="size-5"
          /></span><UBadge
            :color="item.is_active ? 'success' : 'neutral'"
            variant="soft"
          >
            {{ item.is_active ? 'Active' : 'Inactive' }}
          </UBadge>
        </div><h3 class="mt-5 text-lg font-semibold">
          {{ item.name }}
        </h3><p class="mt-1 text-sm text-muted">
          {{ item.code || 'No code' }}<span v-if="item.city"> · {{ item.city }}</span>
        </p><div class="mt-5 flex items-center gap-2 text-sm text-muted">
          <UIcon name="i-lucide-network" />{{ item.departments?.length || data?.departments.filter(dept => dept.unit_id === item.id).length || 0 }} departments
        </div><div v-if="false" class="mt-5 flex justify-end gap-1">
          <UButton icon="i-lucide-pencil" color="neutral" variant="ghost" aria-label="Edit unit" title="Edit unit" @click="openEdit(item)" /><USwitch size="sm" class="shrink-0" :model-value="item.is_active" :aria-label="item.is_active ? 'Disable unit' : 'Enable unit'" @update:model-value="toggleItem(item)" /><UButton icon="i-lucide-trash-2" color="error" variant="ghost" aria-label="Delete unit" title="Delete unit" @click="deleteItem(item)" />
        </div>
      </article>
    </section>
    <section
      v-else-if="activeTab === 'departments'"
      class="people-card mt-5 overflow-hidden"
    >
      <div class="divide-y divide-[var(--people-border)]">
        <article
          v-for="item in data?.departments"
          :key="item.id"
          class="flex items-center gap-4 p-5 sm:px-6"
        >
          <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-[var(--people-mint)]"><UIcon name="i-lucide-network" /></span><div class="min-w-0 flex-1">
            <h3 class="truncate font-semibold">
              {{ item.name }}
            </h3><p class="mt-1 text-sm text-muted">
              {{ unitName(item.unit_id) }} · {{ item.code || 'No code' }}
            </p>
          </div><UBadge
            :color="item.is_active ? 'success' : 'neutral'"
            variant="soft"
          >
            {{ item.is_active ? 'Active' : 'Inactive' }}
          </UBadge><div v-if="false" class="flex shrink-0 gap-1">
            <UButton icon="i-lucide-pencil" color="neutral" variant="ghost" aria-label="Edit department" title="Edit department" @click="openEdit(item)" /><USwitch size="sm" class="shrink-0" :model-value="item.is_active" :aria-label="item.is_active ? 'Disable department' : 'Enable department'" @update:model-value="toggleItem(item)" /><UButton icon="i-lucide-trash-2" color="error" variant="ghost" aria-label="Delete department" title="Delete department" @click="deleteItem(item)" />
          </div>
        </article>
      </div>
    </section>
    <section
      v-else
      class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <article
        v-for="item in data?.designations"
        :key="item.id"
        class="people-card p-5"
      >
        <div class="flex items-start justify-between">
          <span class="grid size-10 place-items-center rounded-xl bg-[var(--people-lavender)]"><UIcon name="i-lucide-badge" /></span><UBadge
            :color="item.is_active ? 'success' : 'neutral'"
            variant="soft"
          >
            {{ item.is_active ? 'Active' : 'Inactive' }}
          </UBadge>
        </div><h3 class="mt-5 font-semibold">
          {{ item.name }}
        </h3><p class="mt-1 text-xs font-semibold uppercase tracking-wide text-muted">
          {{ item.code || 'No code' }}
        </p><p class="mt-3 line-clamp-2 text-sm text-muted">
          {{ item.description || 'No description provided.' }}
        </p><p class="mt-4 flex items-center justify-end gap-2 text-xs text-muted"><UIcon name="i-lucide-refresh-cw" />Managed by ERP</p>
      </article>
    </section>
    <USlideover
      v-model:open="createOpen"
      :title="`${editingId ? 'Edit' : 'Add'} ${activeTab.slice(0, -1)}`"
    >
      <template #body>
        <form
          id="org-create"
          class="space-y-5"
          @submit.prevent="saveItem"
        >
          <UFormField
            label="Name"
            required
          >
            <UInput
              v-model="form.name"
              class="w-full"
              autofocus
            />
          </UFormField><UFormField label="Code">
            <UInput
              v-model="form.code"
              class="w-full"
            />
          </UFormField><UFormField
            v-if="activeTab === 'units'"
            label="City"
          >
            <UInput
              v-model="form.city"
              class="w-full"
            />
          </UFormField><UFormField
            v-if="activeTab === 'departments'"
            label="Unit"
            required
          >
            <USelect
              v-model="form.unit_id"
              class="w-full"
              :items="(data?.units || []).map(item => ({ label: item.name, value: item.id }))"
            />
          </UFormField><UFormField
            v-if="activeTab === 'designations'"
            label="Description"
          >
            <UTextarea
              v-model="form.description"
              class="w-full"
              :rows="4"
            />
          </UFormField>
        </form>
      </template><template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            color="neutral"
            variant="ghost"
            @click="createOpen = false"
          >
            Cancel
          </UButton><UButton
            type="submit"
            form="org-create"
            :loading="saving"
          >
            Save
          </UButton>
        </div>
      </template>
    </USlideover>
  </div>
</template>
