<script setup lang="ts">
useHead({
  htmlAttrs: { lang: 'en' },
  meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' }],
  link: [
    { rel: 'icon', type: 'image/svg+xml', href: '/branding/people-app-icon-violet.svg' },
    { rel: 'apple-touch-icon', href: '/branding/people-app-icon-violet.svg' }
  ]
})

useSeoMeta({
  titleTemplate: title => title ? `${title} · People` : 'People · HRMS',
  description: 'People is the calm, modern workspace for attendance, leave and employee operations.'
})
</script>

<template>
  <UApp>
    <NuxtLoadingIndicator />
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>
