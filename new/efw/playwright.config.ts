import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/ui',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5173', viewport: { width: 1366, height: 768 } },
  webServer: {
    command: `${JSON.stringify(process.execPath)} node_modules/vite/bin/vite.js`,
    url: 'http://127.0.0.1:5173',
    timeout: 120000,
    reuseExistingServer: false,
  },
});
