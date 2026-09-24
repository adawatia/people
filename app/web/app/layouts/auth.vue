<template>
  <div class="min-h-dvh bg-[var(--people-canvas)] px-5 py-8 sm:px-8">
    <header class="mx-auto flex max-w-6xl items-center justify-between">
      <BrandMark />
      <UColorModeButton />
    </header>
    <main class="mx-auto flex min-h-[calc(100dvh-6rem)] max-w-lg items-center py-10">
      <div class="w-full">
        <slot />
      </div>
    </main>
    <footer class="mx-auto flex max-w-lg items-center justify-center gap-2 pb-4 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">
      <span>Powered by</span>
      <img
        src="/branding/dat-labs-symbol-dark.svg"
        alt="Datlabs"
        class="size-4 object-contain dark:hidden"
      >
      <img
        src="/branding/dat-labs-symbol-light.svg"
        alt="Datlabs"
        class="hidden size-4 object-contain dark:block"
      >
      <span>Datlabs</span>
    </footer>
  </div>
</template>
