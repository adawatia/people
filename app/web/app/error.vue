<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()
const isUnavailable = computed(() => (props.error.statusCode ?? 500) >= 500)
</script>

<template>
  <main class="grid min-h-dvh place-items-center bg-[#f5f7f4] p-6 font-sans text-[#1a2920] dark:bg-[#111a15] dark:text-[#ecf5ed]">
    <section
      class="w-full max-w-[540px] rounded-2xl bg-white p-7 shadow-xl sm:p-12 dark:bg-[#1d2a21]"
      role="alert"
    >
      <p class="mb-9 text-sm font-bold text-[#287448] dark:text-[#8ad5a4]">
        Emploi
      </p>
      <h1 class="mb-4 text-3xl leading-tight font-semibold tracking-tight text-balance sm:text-4xl">
        {{ isUnavailable ? 'This page is temporarily unavailable' : 'We could not open this page' }}
      </h1>
      <p class="max-w-[52ch] leading-relaxed text-[#4c6255] dark:text-[#bacdc0]">
        {{ isUnavailable ? 'The service did not respond. Please try again. If the problem continues, contact your administrator.' : 'The page could not be loaded. Try again, or return to sign in.' }}
      </p>
      <div class="mt-8 flex flex-wrap items-center gap-4">
        <a
          href=""
          class="inline-flex min-h-11 items-center rounded-lg bg-[#287448] px-5 py-2.5 font-semibold text-white hover:bg-[#205f3b] focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-[#287448] dark:bg-[#8ad5a4] dark:text-[#132217] dark:hover:bg-[#a5e4b7]"
        >
          Try again
        </a>
        <a
          href="/login"
          class="font-semibold text-[#205f3b] underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-[#287448] dark:text-[#8ad5a4]"
        >Go to sign in</a>
      </div>
    </section>
  </main>
</template>
