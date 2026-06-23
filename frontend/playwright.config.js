import { defineConfig } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: path.resolve(__dirname, 'tests'),
  timeout: 30000,
  retries: 0,
  workers: 1,
  globalSetup: path.resolve(__dirname, 'tests/global-setup.mjs'),
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173',
    headless: true,
    screenshot: 'only-on-failure',
    storageState: path.resolve(__dirname, 'tests/.auth/admin.json'),
  },
  projects: [
    {
      name: 'admin',
      use: {
        storageState: path.resolve(__dirname, 'tests/.auth/admin.json'),
      },
    },
  ],
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVER === '1' ? undefined : {
    command: 'npm run dev',
    port: 5173,
    timeout: 120000,
    reuseExistingServer: true,
  },
});
