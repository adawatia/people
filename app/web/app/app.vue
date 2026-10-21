<script setup lang="ts">
useHead({
  htmlAttrs: { lang: 'en' },
  meta: [
    { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
    { name: 'theme-color', content: '#1d613a' }
  ],
  link: [
    { rel: 'manifest', href: '/manifest.webmanifest' },
    { rel: 'icon', href: '/branding/people-app-icon-violet.svg', type: 'image/svg+xml' },
    { rel: 'apple-touch-icon', href: '/branding/people-app-icon-192.png', sizes: '192x192' }
  ]
})

useSeoMeta({
  titleTemplate: title => title ? `${title} · Emploi` : 'Emploi · HRMS',
  description: 'Emploi is the calm, modern workspace for attendance, leave and employee operations.'
})

onMounted(() => {
  if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch((error: unknown) => {
      console.warn('Emploi offline support could not be enabled.', error)
    })
  }
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
