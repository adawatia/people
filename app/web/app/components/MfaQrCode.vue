<script setup lang="ts">
/**
 * The scanning half of authenticator setup.
 *
 * A 32-character base32 setup key is the kind of thing people mistype, so the QR
 * is the primary route and manual entry is the fallback. The code is generated
 * in the browser from the provisioning URI: the secret therefore travels only in
 * the JSON body it arrived in, never in a URL or query string where it would be
 * written to access logs and browser history.
 */
import QRCode from 'qrcode'

const props = defineProps<{
  /** The `otpauth://` URI from the API. */
  uri: string
  /** Setup key, shown for manual entry and grouped for readability. */
  secret: string
}>()

const dataUrl = ref('')
const failure = ref('')
const revealed = ref(false)

/** Base32 keys are transcribed four characters at a time. */
const groupedSecret = computed(() => (props.secret.match(/.{1,4}/g) ?? []).join(' '))

async function render() {
  failure.value = ''
  try {
    dataUrl.value = await QRCode.toDataURL(props.uri, {
      errorCorrectionLevel: 'M',
      margin: 1,
      width: 240,
      color: { dark: '#14121f', light: '#ffffff' }
    })
  } catch {
    // A failed render must not hide the setup key: manual entry still works.
    failure.value = 'The QR code could not be drawn. Use the setup key below.'
  }
}

// Client-only: the renderer needs a canvas, and the component only ever runs
// inside an authenticated page anyway.
onMounted(render)
watch(() => props.uri, render)
</script>

<template>
  <div class="space-y-3">
    <div class="flex justify-center rounded-xl border border-[var(--people-border)] bg-white p-3">
      <img
        v-if="dataUrl"
        :src="dataUrl"
        alt="QR code containing your authenticator setup key"
        class="size-52"
        width="208"
        height="208"
      >
      <div
        v-else
        class="grid size-52 place-items-center text-center text-xs text-muted"
      >
        <span v-if="failure">{{ failure }}</span>
        <span v-else>Preparing your QR code…</span>
      </div>
    </div>

    <div>
      <button
        type="button"
        class="text-xs font-medium text-primary underline-offset-4 hover:underline"
        @click="revealed = !revealed"
      >
        {{ revealed ? 'Hide setup key' : 'Can’t scan? Enter the key manually' }}
      </button>
      <div
        v-if="revealed"
        class="mt-2 rounded-lg border border-[var(--people-border)] p-3"
      >
        <p class="text-xs font-medium uppercase tracking-wide text-muted">
          Setup key
        </p>
        <p class="mt-1 font-mono text-sm break-all">
          {{ groupedSecret }}
        </p>
        <p class="mt-2 text-xs text-muted">
          In your authenticator app choose “Enter a setup key” and pick Time-based.
        </p>
      </div>
    </div>
  </div>
</template>
