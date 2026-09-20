<script setup lang="ts">
/* eslint-disable better-tailwindcss/no-unknown-classes, @stylistic/max-statements-per-line */
import type { Unit } from '#shared/types/organization'
import type { HolidayList } from '#shared/types/workforce'

useSeoMeta({ title: 'Holidays' })
const api = useHrmsApi(); const auth = useAuth(); const toast = useToast(); const selectedId = ref<number>(); const createOpen = ref(false); const holidayOpen = ref(false); const saving = ref(false)
const year = new Date().getFullYear(); const form = reactive({ name: `${year} Holiday Calendar`, from_date: `${year}-01-01`, to_date: `${year}-12-31`, weekly_off_day: 'Sunday', unit_id: undefined as number | undefined, is_default: false }); const holiday = reactive({ name: '', holiday_date: `${year}-01-01`, description: '' })
const canManage = computed(() => auth.hasPermission('system.configure'))
const { data, pending, error, refresh } = await useAsyncData('holiday-workspace', async () => { const [lists, units] = await Promise.all([api.request<HolidayList[]>('holidays/lists'), api.request<Unit[]>('org/units')]); return { lists, units } })
watchEffect(() => { if (!selectedId.value && data.value?.lists[0]) selectedId.value = data.value.lists[0].id })
const selected = computed(() => data.value?.lists.find(item => item.id === selectedId.value))
const formatDate = (value: string) => new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(`${value}T00:00:00`))
async function createList() { saving.value = true; try { await api.request('holidays/lists', { method: 'POST', body: form }); createOpen.value = false; toast.add({ title: 'Holiday calendar created', color: 'success' }); await refresh() } finally { saving.value = false } }
async function addHoliday() { if (!selected.value || !holiday.name.trim()) return; saving.value = true; try { await api.request(`holidays/lists/${selected.value.id}/holidays`, { method: 'POST', body: { ...holiday, holiday_list_id: selected.value.id } }); holidayOpen.value = false; toast.add({ title: 'Holiday added', color: 'success' }); await refresh() } finally { saving.value = false } }
</script>

<template>
  <div>
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">
          Work calendar
        </p><h2 class="mt-1 text-2xl font-semibold sm:text-3xl">
          Holidays
        </h2><p class="mt-2 text-sm text-muted">
          View holiday calendars and automatically generated weekly offs.
        </p>
      </div><UButton
        v-if="canManage"
        icon="i-lucide-calendar-plus"
        size="lg"
        @click="createOpen = true"
      >
        New calendar
      </UButton>
    </div><UAlert
      v-if="error"
      class="mt-6"
      color="error"
      variant="soft"
      title="Holiday calendars are unavailable"
      :actions="[{ label: 'Try again', onClick: () => refresh() }]"
    /><div
      v-else
      class="mt-7 grid gap-5 lg:grid-cols-[20rem_1fr]"
    >
      <aside class="people-card h-fit overflow-hidden">
        <div class="border-b border-[var(--people-border)] p-4">
          <h3 class="font-semibold">
            Calendars
          </h3>
        </div><div
          v-if="pending"
          class="space-y-3 p-4"
        >
          <USkeleton
            v-for="i in 3"
            :key="i"
            class="h-16"
          />
        </div><button
          v-for="item in data?.lists"
          v-else
          :key="item.id"
          class="flex w-full items-center gap-3 border-b border-[var(--people-border)] p-4 text-left last:border-0"
          :class="selectedId === item.id ? 'bg-primary-50 dark:bg-primary-950/20' : 'hover:bg-muted/5'"
          @click="selectedId = item.id"
        >
          <span class="grid size-10 place-items-center rounded-xl bg-[var(--people-lavender)]"><UIcon name="i-lucide-calendar-days" /></span><span class="min-w-0 flex-1"><span class="block truncate font-medium">{{ item.name }}</span><span class="mt-1 block text-xs text-muted">{{ item.weekly_off_day }} weekly off</span></span><UBadge
            v-if="item.is_default"
            color="primary"
            variant="soft"
            size="sm"
          >
            Default
          </UBadge>
        </button>
      </aside><section class="people-card overflow-hidden">
        <div class="flex flex-col gap-3 border-b border-[var(--people-border)] p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <h3 class="font-semibold">
              {{ selected?.name || 'Select a calendar' }}
            </h3><p
              v-if="selected"
              class="mt-1 text-sm text-muted"
            >
              {{ selected.from_date }} – {{ selected.to_date }}
            </p>
          </div><UButton
            v-if="selected && canManage"
            color="neutral"
            variant="soft"
            icon="i-lucide-plus"
            @click="holidayOpen = true"
          >
            Add holiday
          </UButton>
        </div><div
          v-if="selected && !selected.holidays.length"
          class="p-12 text-center text-sm text-muted"
        >
          No holidays in this calendar.
        </div><div
          v-else
          class="divide-y divide-[var(--people-border)]"
        >
          <article
            v-for="item in selected?.holidays"
            :key="item.id"
            class="flex items-center gap-4 p-4 sm:px-6"
          >
            <div class="w-20 shrink-0 text-sm font-semibold">
              {{ formatDate(item.holiday_date) }}
            </div><span
              class="grid size-10 shrink-0 place-items-center rounded-xl"
              :class="item.is_weekly_off ? 'bg-muted/10' : 'bg-[var(--people-peach)]'"
            ><UIcon :name="item.is_weekly_off ? 'i-lucide-calendar-off' : 'i-lucide-party-popper'" /></span><div class="min-w-0 flex-1">
              <p class="font-medium">
                {{ item.name }}
              </p><p class="mt-1 truncate text-xs text-muted">
                {{ item.description || (item.is_weekly_off ? 'Weekly off' : 'Organization holiday') }}
              </p>
            </div>
          </article>
        </div>
      </section>
    </div><USlideover
      v-model:open="createOpen"
      title="New holiday calendar"
    >
      <template #body>
        <form
          id="holiday-list"
          class="space-y-5"
          @submit.prevent="createList"
        >
          <UFormField label="Name">
            <UInput
              v-model="form.name"
              class="w-full"
            />
          </UFormField><div class="grid grid-cols-2 gap-4">
            <UFormField label="From">
              <UInput
                v-model="form.from_date"
                type="date"
                class="w-full"
              />
            </UFormField><UFormField label="To">
              <UInput
                v-model="form.to_date"
                type="date"
                class="w-full"
              />
            </UFormField>
          </div><UFormField label="Weekly off">
            <USelect
              v-model="form.weekly_off_day"
              class="w-full"
              :items="['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']"
            />
          </UFormField><UFormField label="Unit">
            <USelect
              v-model="form.unit_id"
              class="w-full"
              :items="(data?.units || []).map(item => ({ label: item.name, value: item.id }))"
            />
          </UFormField><UCheckbox
            v-model="form.is_default"
            label="Use as default calendar"
          />
        </form>
      </template><template #footer>
        <UButton
          type="submit"
          form="holiday-list"
          block
          :loading="saving"
        >
          Create calendar
        </UButton>
      </template>
    </USlideover><UModal
      v-model:open="holidayOpen"
      title="Add holiday"
    >
      <template #body>
        <form
          id="holiday-add"
          class="space-y-5"
          @submit.prevent="addHoliday"
        >
          <UFormField label="Holiday name">
            <UInput
              v-model="holiday.name"
              class="w-full"
            />
          </UFormField><UFormField label="Date">
            <UInput
              v-model="holiday.holiday_date"
              type="date"
              class="w-full"
            />
          </UFormField><UFormField label="Description">
            <UTextarea
              v-model="holiday.description"
              class="w-full"
            />
          </UFormField>
        </form>
      </template><template #footer>
        <UButton
          type="submit"
          form="holiday-add"
          block
          :loading="saving"
        >
          Add holiday
        </UButton>
      </template>
    </UModal>
  </div>
</template>
