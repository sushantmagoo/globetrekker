import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests run against the real Docker stack (Vite dev server → FastAPI → Postgres).
 * Start it first (see README / `make e2e`), with RATE_LIMIT_ENABLED=false so tests can sign
 * up many users. BASE_URL defaults to the local dev stack.
 */
export default defineConfig({
  testDir: './tests',
  globalSetup: './tests/global-setup.ts',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  // Tests share one database; each creates its own uniquely named users, so they can run in
  // parallel without stepping on each other.
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] }, grep: /@mobile/ },
  ],
})
