import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/auth',
  outputDir: './test-results/auth',
  timeout: 30000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:3100',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, args: ['--no-sandbox'] }
      : {}
  },
  webServer: {
    command: 'pnpm dev --host 127.0.0.1 --port 3100',
    url: 'http://127.0.0.1:3100/login',
    reuseExistingServer: true,
    timeout: 120000
  }
})
