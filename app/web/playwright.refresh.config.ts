import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/refresh',
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:3101',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, args: ['--no-sandbox'] }
      : {}
  },
  webServer: {
    command: 'pnpm dev --host 127.0.0.1 --port 3101',
    url: 'http://127.0.0.1:3101/login',
    env: { NUXT_HRMS_API_BASE: 'http://127.0.0.1:3901' },
    reuseExistingServer: false,
    timeout: 120000
  }
})
