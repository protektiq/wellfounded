import * as fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("country conditions memo with stubbed generation", async ({ page }) => {
  const raw = fs.readFileSync(
    path.join(__dirname, ".auth", "fixture.json"),
    "utf-8",
  );
  const { case_id } = JSON.parse(raw) as { case_id: string };
  await page.goto(`/cases/${case_id}/country-conditions`);
  await expect(
    page.getByRole("heading", { name: "Request a new memo" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Generate memo" }).click();
  await page.waitForURL(
    (url) => /\/country-conditions\/[0-9a-f-]{36}$/i.test(url.pathname),
    { timeout: 120_000 },
  );
  await expect(page.getByText("E2E seeded passage text")).toBeVisible({
    timeout: 120_000,
  });
  await page.getByLabel(/Open source for citation/).first().click();
  await expect(page.getByRole("heading", { name: "Cited source" })).toBeVisible();
});
