export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@nuxt/icon',
    '@nuxt/image',
    'nuxt-auth-utils',
    'nuxt-echarts'
  ],

  devtools: {
    enabled: true
  },

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    hrmsApiBase: import.meta.env.NUXT_HRMS_API_BASE || 'http://127.0.0.1:8000'
  },

  compatibilityDate: '2026-06-30',

  // Keep owner-dashboard charts small: only register the chart primitives
  // used by the application. VChart is auto-imported by nuxt-echarts.
  echarts: {
    renderer: ['canvas', 'svg'],
    charts: ['BarChart', 'LineChart', 'PieChart'],
    components: ['GridComponent', 'LegendComponent', 'TooltipComponent', 'DataZoomComponent'],
    features: ['LabelLayout', 'UniversalTransition']
  },

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  }
})
