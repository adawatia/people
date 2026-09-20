<script setup lang="ts">
import type { AttendancePunch } from '#shared/types/attendance'

const props = defineProps<{
  employeeId: number
  punches: AttendancePunch[]
}>()
const emit = defineEmits<{ punched: [] }>()
const api = useHrmsApi()
const toast = useToast()
const now = ref(new Date())
const loading = ref(false)
const locationState = ref<'idle' | 'requesting' | 'ready' | 'denied'>('idle')
const pendingWithoutLocation = ref(false)
let clock: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  clock = setInterval(() => {
    now.value = new Date()
  }, 1000)
})
onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
})

const latestPunch = computed(() => [...props.punches].sort((a, b) => Date.parse(b.punch_time) - Date.parse(a.punch_time))[0])
const nextType = computed<'IN' | 'OUT'>(() => latestPunch.value?.punch_type === 'IN' ? 'OUT' : 'IN')
const hasOpenShift = computed(() => nextType.value === 'OUT')

function getPosition() {
  return new Promise<GeolocationPosition>((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error('Geolocation is unavailable'))
    navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 })
  })
}

async function submitPunch(withLocation = true) {
  loading.value = true
  pendingWithoutLocation.value = false
  let latitude: number | undefined
  let longitude: number | undefined
  try {
    if (withLocation) {
      locationState.value = 'requesting'
      try {
        const position = await getPosition()
        latitude = position.coords.latitude
        longitude = position.coords.longitude
        locationState.value = 'ready'
      } catch {
        locationState.value = 'denied'
        pendingWithoutLocation.value = true
        return
      }
    }

    await api.request<AttendancePunch>('attendance/checkins', {
      method: 'POST',
      body: {
        employee_id: props.employeeId,
        punch_time: new Date().toISOString(),
        punch_type: nextType.value,
        source: 'WEB',
        latitude,
        longitude
      }
    })
    toast.add({ title: nextType.value === 'IN' ? 'You’re checked in' : 'You’re checked out', color: 'success', icon: 'i-lucide-circle-check' })
    emit('punched')
  } catch (error) {
    const candidate = error as { data?: { statusMessage?: string } }
    toast.add({ title: 'Punch was not recorded', description: candidate.data?.statusMessage || 'Please try again.', color: 'error', icon: 'i-lucide-circle-alert' })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="overflow-hidden rounded-2xl bg-[#27213f] text-white shadow-xl shadow-violet-950/10">
    <div class="relative p-6 sm:p-7">
      <div class="absolute -right-14 -top-16 size-48 rounded-full bg-violet-400/20 blur-2xl" />
      <div class="relative">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-medium text-violet-100/70">
              Current time
            </p>
            <p class="mt-2 text-4xl font-semibold tracking-tight tabular-nums">
              {{ new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(now) }}
            </p>
            <p class="mt-2 text-sm text-violet-100/70">
              {{ new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long' }).format(now) }}
            </p>
          </div>
          <span class="grid size-11 place-items-center rounded-2xl bg-white/10"><UIcon
            :name="hasOpenShift ? 'i-lucide-briefcase-business' : 'i-lucide-coffee'"
            class="size-5"
          /></span>
        </div>

        <div
          v-if="latestPunch"
          class="mt-6 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm"
        >
          Last {{ latestPunch.punch_type === 'IN' ? 'check-in' : 'check-out' }} at
          <strong class="ml-1 tabular-nums">{{ new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit' }).format(new Date(latestPunch.punch_time)) }}</strong>
        </div>

        <UButton
          class="mt-5"
          block
          size="xl"
          color="neutral"
          :icon="nextType === 'IN' ? 'i-lucide-log-in' : 'i-lucide-log-out'"
          :loading="loading"
          @click="submitPunch(true)"
        >
          {{ nextType === 'IN' ? 'Check in now' : 'Check out now' }}
        </UButton>
        <p class="mt-3 flex items-center justify-center gap-1.5 text-center text-xs text-violet-100/60">
          <UIcon name="i-lucide-map-pin" /> Your location is requested only when you punch.
        </p>
      </div>
    </div>

    <div
      v-if="pendingWithoutLocation"
      class="border-t border-white/10 bg-white/5 p-5"
    >
      <p class="text-sm font-semibold">
        Location wasn’t available
      </p>
      <p class="mt-1 text-xs leading-5 text-violet-100/70">
        You can retry after enabling browser location, or continue without it if your workplace policy allows.
      </p>
      <div class="mt-4 flex gap-2">
        <UButton
          size="sm"
          color="neutral"
          variant="soft"
          @click="submitPunch(true)"
        >
          Retry location
        </UButton>
        <UButton
          size="sm"
          color="neutral"
          variant="ghost"
          @click="submitPunch(false)"
        >
          Continue without location
        </UButton>
      </div>
    </div>
  </section>
</template>
