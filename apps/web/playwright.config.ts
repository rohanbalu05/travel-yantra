import { defineConfig } from "@playwright/test";

// The demo path in the browser, on the mock API (no live calls): `pnpm build && pnpm e2e`.
const port = process.env.E2E_PORT ?? "3100";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  projects: [
    { name: "laptop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "phone", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: {
    command: "node e2e/serve.mjs",
    url: `http://127.0.0.1:${port}/home/`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
