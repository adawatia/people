<script setup lang="ts">
useHead({
  htmlAttrs: { lang: 'en' },
  meta: [
    { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
    { name: 'theme-color', content: '#1d613a' }
  ],
  link: [
    { rel: 'icon', href: '/favicon.ico', sizes: '48x48' },
    { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' },
    { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' }
  ]
})

useSeoMeta({
  titleTemplate: title => title ? `${title} · Emploi` : 'Emploi · HRMS',
  description: 'Emploi is the calm, modern workspace for attendance, leave and employee operations.',
  ogTitle: 'Emploi — HR made calm',
  ogDescription: 'Emploi is the calm, modern workspace for attendance, leave and employee operations.',
  ogImage: '/og-image.png',
  twitterCard: 'summary_large_image',
  twitterImage: '/og-image.png'
})
</script>

<template>
  <UApp>
    <NuxtLoadingIndicator />
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
    <ClientOnly>
      <PwaUpdatePrompt />
    </ClientOnly>
  </UApp>
</template>
