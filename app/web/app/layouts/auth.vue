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
  </div>
</template>
