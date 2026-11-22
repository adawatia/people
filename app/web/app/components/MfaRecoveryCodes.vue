<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    codes: string[]
    title?: string
    description?: string
    filename?: string
    dismissable?: boolean
  }>(),
  {
    title: 'Recovery codes (shown once)',
    description: 'Store these somewhere safe. Each one signs you in once if you lose your device.',
    filename: 'people-mfa-recovery-codes.txt',
    dismissable: false
  }
)

const emit = defineEmits<{
  dismiss: []
}>()

const toast = useToast()
const copied = ref(false)
const downloaded = ref(false)

const validCodes = computed(() => (props.codes ?? []).filter(c => typeof c === 'string' && c.trim().length > 0))

function downloadCodes() {
  if (!validCodes.value.length) return

  const formattedDate = new Date().toISOString().replace('T', ' ').slice(0, 19)
  const header = [
    'People HRMS - MFA Recovery Codes',
    '============================================================',
    `Generated: ${formattedDate} UTC`,
    '',
    'Keep these single-use recovery codes in a safe, secure place.',
    'Each code can be used once as a backup login method if you',
    'lose access to your authenticator app.',
    '============================================================',
    ''
  ]

  const formattedCodes = validCodes.value.map((code, index) => {
    const num = String(index + 1).padStart(2, '0')
    return `${num}. ${code}`
  })

  const footer = [
    '',
    '============================================================',
    'Treat these recovery codes with the same confidentiality as',
    'your primary password. Do not share them with anyone.',
    '============================================================'
  ]

  const textContent = [...header, ...formattedCodes, ...footer].join('\n')
  const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = props.filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)

  // Asynchronous cleanup so slow engines don't terminate download before starting
  setTimeout(() => {
    URL.revokeObjectURL(url)
  }, 1000)

  downloaded.value = true
  setTimeout(() => {
    downloaded.value = false
  }, 2500)

  toast.add({
    title: 'Recovery codes downloaded',
    description: `Saved to ${props.filename}`,
    color: 'success'
  })
}

async function copyCodes() {
  if (!validCodes.value.length) return
  const text = validCodes.value.join('\n')

  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }

    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2500)

    toast.add({
      title: 'Recovery codes copied',
      description: 'All recovery codes have been copied to your clipboard.',
      color: 'success'
    })
  } catch {
    toast.add({
      title: 'Copy unavailable',
      description: 'Select and copy the recovery codes manually.',
      color: 'warning'
    })
  }
}
</script>

<template>
  <div
    v-if="validCodes.length"
    class="space-y-2"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-xs font-medium uppercase tracking-wide text-muted">
        {{ title }}
      </p>
      <div class="flex items-center gap-1.5">
        <UButton
          type="button"
          size="xs"
          variant="subtle"
          :icon="downloaded ? 'i-lucide-check' : 'i-lucide-download'"
          @click="downloadCodes"
        >
          {{ downloaded ? 'Downloaded' : 'Download (.txt)' }}
        </UButton>
        <UButton
          type="button"
          size="xs"
          variant="ghost"
          :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
          @click="copyCodes"
        >
          {{ copied ? 'Copied' : 'Copy all' }}
        </UButton>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-1.5 rounded-lg border border-[var(--people-border)] bg-muted/5 p-3 font-mono text-xs sm:grid-cols-2">
      <div
        v-for="(recovery, index) in validCodes"
        :key="recovery"
        class="flex items-center justify-between rounded px-2 py-1 text-xs tracking-wider"
      >
        <span class="select-none text-muted">{{ String(index + 1).padStart(2, '0') }}.</span>
        <span class="font-semibold">{{ recovery }}</span>
      </div>
    </div>

    <p class="text-xs text-muted">
      {{ description }}
    </p>

    <div
      v-if="dismissable"
      class="pt-1"
    >
      <UButton
        type="button"
        variant="ghost"
        size="sm"
        @click="emit('dismiss')"
      >
        I’ve saved them
      </UButton>
    </div>
  </div>
</template>
