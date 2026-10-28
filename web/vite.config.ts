import { defineConfig } from 'vitest/config';

export default defineConfig({
  base: '/policydesk/',
  test: { include: ['tests/**/*.test.ts'] },
  server: { host: '127.0.0.1', port: 5177, strictPort: true },
  preview: { host: '127.0.0.1', port: 4177, strictPort: true },
});
