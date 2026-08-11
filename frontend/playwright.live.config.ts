import { defineConfig, devices } from "@playwright/test";

const liveUrl = process.env.SHOPMIND_FRONTEND_URL ?? "http://127.0.0.1:5173";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "live-critical-path.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "line",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: liveUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
});
