import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  outputDir: '../.runtime/browser-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4177/policydesk/',
    channel: process.env.CI ? undefined : 'msedge',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run preview',
    url: 'http://127.0.0.1:4177/policydesk/',
    reuseExistingServer: !process.env.CI,
    timeout: 20000,
  },
});
