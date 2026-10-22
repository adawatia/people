<script setup lang="ts">
const route = useRoute()
const isTechnical = computed(() => route.path.startsWith('/admin'))
const brandLink = computed(() => (isTechnical.value ? '/admin/login' : '/login'))
const brandLabel = computed(() => (isTechnical.value ? 'Emploi — technical administration' : 'Emploi — sign in'))
</script>

<template>
  <NuxtLink
    :to="brandLink"
    class="auth-brand"
    :aria-label="brandLabel"
  >
    <EmploiLogo :size="38" />
  </NuxtLink>
</template>
