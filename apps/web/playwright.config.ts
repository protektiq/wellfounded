import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 30_000 },
  forbidOnly: !!process.env.CI,
  globalSetup: path.join(__dirname, "e2e", "global-setup.ts"),
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000",
    storageState: path.join(__dirname, "e2e", ".auth", "storage.json"),
  },
});
