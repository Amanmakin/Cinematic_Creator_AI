import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",

  // Each test can take up to 10 minutes (LLM + Blender + render)
  timeout: 10 * 60 * 1000,

  // Expect assertions default to 10 s (element waits inside gates)
  expect: { timeout: 10_000 },

  // Run tests in a single worker so both approval gates are handled
  // sequentially and don't race against each other.
  workers: 1,

  // Keep a detailed HTML report alongside the test run
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }], ["list"]],

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",

    // Record a trace for every run so failures are debuggable
    trace: "on",

    // Record video on first retry
    video: "on-first-retry",

    // Headless by default; set PWHEADLESS=false to watch live
    headless: process.env.PWHEADLESS !== "false",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Start the Next.js dev server if it isn't already running.
  // The API server (FastAPI on :8000) must be started separately:
  //   cd apps/api && uv run uvicorn api.main:app --reload
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
