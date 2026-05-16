import * as fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

const audioFixture = path.join(
  __dirname,
  "..",
  "..",
  "api",
  "tests",
  "fixtures",
  "audio",
  "es.wav",
);

test("declaration flow with stubbed generation", async ({ page }) => {
  const raw = fs.readFileSync(
    path.join(__dirname, ".auth", "fixture.json"),
    "utf-8",
  );
  const { case_id } = JSON.parse(raw) as { case_id: string };

  await page.goto(`/cases/${case_id}/declarations/new`);
  await expect(
    page.getByRole("heading", { name: "Request a first draft" }),
  ).toBeVisible();

  await page.getByLabel("Interview audio").setInputFiles(audioFixture);
  await page.getByRole("button", { name: "Request first draft" }).click();

  await page.waitForURL(
    (url) => /\/declarations\/[0-9a-f-]{36}$/i.test(url.pathname),
    { timeout: 180_000 },
  );

  await expect(
    page.getByText("First incident date not stated", { exact: false }),
  ).toBeVisible({ timeout: 180_000 });

  await page.getByRole("button", { name: "Accept" }).first().click();
  await page.waitForTimeout(1500);

  await page.getByRole("button", { name: "Edit" }).first().click();
  await expect(page.getByRole("heading", { name: /INCONSISTENCY/i })).toBeVisible();
  await page.getByLabel("Edited resolution text").fill(
    "Confirm with client whether there were three or four men at the incident.",
  );
  await page.getByRole("button", { name: "Apply edit" }).click();

  await page.getByLabel("Instruction").fill("Clarify the well-founded fear section.");
  await page.getByLabel("Target scope").selectOption({
    label: "Section: Well-founded fear of future harm",
  });
  await page.getByRole("button", { name: "Request revision" }).click();
  await page.waitForURL(
    (url) => /\/declarations\/[0-9a-f-]{36}$/i.test(url.pathname),
    { timeout: 120_000 },
  );

  const acceptButtons = page.getByRole("button", { name: "Accept" });
  const count = await acceptButtons.count();
  for (let i = 0; i < count; i += 1) {
    await acceptButtons.first().click();
    await page.waitForTimeout(500);
  }

  const cleanBtn = page.getByRole("button", { name: "Clean copy" });
  await expect(cleanBtn).toBeEnabled({ timeout: 30_000 });

  const downloadPromise = page.waitForEvent("download");
  await cleanBtn.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.docx$/i);

  await page.getByRole("button", { name: /Play transcript from/ }).first().click();
  const played = await page.evaluate(() => {
    const el = document.querySelector("audio");
    return el !== null && el.currentTime > 0;
  });
  expect(played).toBe(true);
});
