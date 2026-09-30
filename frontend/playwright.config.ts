import { defineConfig, devices } from '@playwright/test';

// E2E_BASE_URL=https://… runs the journeys against a hosted site (no local servers); they add clearly synthetic clients there.
const hosted = process.env.E2E_BASE_URL?.replace(/\/$/, '');
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, retries: 0,
  timeout: 120_000, expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: hosted || 'http://127.0.0.1:3100', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: hosted ? undefined : [
    { command: 'python scripts/serve_e2e.py', cwd: '..', url: 'http://127.0.0.1:8002/health/ready', reuseExistingServer: false, timeout: 120_000 },
    { command: 'npm run dev -- --hostname 127.0.0.1 --port 3100', url: 'http://127.0.0.1:3100', reuseExistingServer: false, timeout: 180_000, env: { API_URL: 'http://127.0.0.1:8002' } },
  ],
});
