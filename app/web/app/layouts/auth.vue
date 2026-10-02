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
        aria-label="About People"
      >
        <div class="auth-story-copy">
          <h2>A little more clarity. Every workday.</h2>
        </div>
        <AuthWorkdayArt :technical="technical" />
        <div class="auth-story-bottom">
          <span>Made for the everyday</span>
          <span>People by Datlabs</span>
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
          src="/branding/dat-labs-symbol-dark.svg"
          alt=""
          class="auth-datlabs-light"
          width="30"
          height="30"
        >
        <img
          src="/branding/dat-labs-symbol-light.svg"
          alt=""
          class="auth-datlabs-dark"
          width="30"
          height="30"
        >
        Thoughtfully built by Datlabs
      </span>
    </footer>
  </div>
</template>
