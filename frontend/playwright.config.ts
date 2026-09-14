import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for the P-234 PolicyMate AI frontend E2E suite.
 *
 * Targets the local dev servers that the CI / developer has running:
 *   - Frontend: http://localhost:3000  (next dev)
 *   - Backend:  http://localhost:8000   (uvicorn)
 *
 * The suite expects the DB and R2 bucket to be in a clean state from
 * ``scripts/e2e_full_smoke.py --phases reset``. The reset phase
 * truncates the public schema, recreates the Qdrant collection, and
 * seeds the demo accounts used by the quick-login buttons.
 *
 * Run the full suite:
 *   cd frontend && npm install && npx playwright install --with-deps chromium
 *   npm run test:e2e
 *
 * Run with the Playwright UI:
 *   npm run test:e2e:ui
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI
    ? [["github"], ["json", { outputFile: "e2e-results.json" }]]
    : [["list"]],

  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: undefined,
  /*
   * If you want the Playwright test runner to start the dev servers
   * automatically, replace the ``webServer: undefined`` block above with:
   *
   *   webServer: {
   *     command: "npm run dev",
   *     url: "http://localhost:3000",
   *     reuseExistingServer: true,
   *     cwd: process.cwd(),
   *   },
   */
});
