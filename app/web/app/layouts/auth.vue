<script setup lang="ts">
useHead({ titleTemplate: '%s' })
const route = useRoute()
const technical = computed(() => route.path === '/admin/login')
const recovery = computed(() => route.path === '/forgot-password')
const year = useState('auth-copyright-year', () => new Date().getFullYear())
</script>

<template>
  <div
    class="auth-shell"
    :class="{ 'auth-shell--technical': technical }"
  >
    <header class="auth-header">
      <AuthBrand />
      <div class="auth-header-actions">
        <ClientOnly>
          <UColorModeButton class="auth-theme-toggle" />
          <template #fallback>
            <span
              class="auth-theme-toggle"
              aria-hidden="true"
            />
          </template>
        </ClientOnly>
      </div>
    </header>
    <main class="auth-main">
      <section
        v-if="!technical"
        class="auth-story"
        aria-label="About Emploi"
      >
        <div class="auth-story-copy">
          <h2>A little more clarity. Every workday.</h2>
        </div>
        <AuthWorkdayArt :technical="technical" />
        <div class="auth-story-bottom">
          <span>Made for the everyday</span>
          <span>Emploi</span>
        </div>
      </section>
      <section
        class="auth-form-region"
        :aria-label="technical ? 'Technical sign-in' : recovery ? 'Account recovery' : 'Workforce sign-in'"
      >
        <div class="auth-form-content">
          <slot />
        </div>
      </section>
    </main>
    <footer class="auth-footer">
      <span>© {{ year }} Datlabs. All rights reserved.</span>
      <span class="auth-footer-maker">
        <img
          src="/brand/lockup-light.svg"
          alt="Datlabs"
          class="auth-datlabs-light h-6 w-auto"
          width="90"
          height="24"
        >
        <img
          src="/brand/lockup-dark.svg"
          alt="Datlabs"
          class="auth-datlabs-dark h-6 w-auto"
          width="90"
          height="24"
        >
      </span>
    </footer>
  </div>
</template>
