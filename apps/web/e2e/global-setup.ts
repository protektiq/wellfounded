import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import path from "node:path";

import type { FullConfig } from "@playwright/test";

const globalSetup = async (config: FullConfig): Promise<void> => {
  void config;
  const secret = process.env.WF_E2E_MAGIC_LINK_SECRET;
  if (secret === undefined || secret.length === 0 || secret.length > 256) {
    throw new Error(
      "WF_E2E_MAGIC_LINK_SECRET must be set (1-256 characters) for Playwright global setup.",
    );
  }
  const api = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8000";
  const apiRoot = path.join(process.cwd(), "..", "api");
  const raw = execFileSync(
    "poetry",
    ["run", "python", "-m", "scripts.e2e_seed_country_conditions"],
    { cwd: apiRoot, encoding: "utf-8", maxBuffer: 10 * 1024 * 1024 },
  );
  const lines = raw.trim().split("\n").filter((l) => l.length > 0);
  const line = lines[lines.length - 1];
  if (line === undefined) {
    throw new Error("e2e seed script produced no output");
  }
  const parsed = JSON.parse(line) as {
    organization_slug: string;
    email: string;
    case_id: string;
  };
  if (
    typeof parsed.organization_slug !== "string" ||
    typeof parsed.email !== "string" ||
    typeof parsed.case_id !== "string"
  ) {
    throw new Error("e2e seed JSON missing required fields");
  }

  const ml = await fetch(`${api}/auth/magic-link`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-E2E-Secret": secret,
    },
    body: JSON.stringify({
      email: parsed.email,
      organization_slug: parsed.organization_slug,
    }),
  });
  if (ml.status !== 200) {
    const t = await ml.text();
    throw new Error(`magic-link reveal failed: ${ml.status} ${t}`);
  }
  const body = (await ml.json()) as { magic_link_url?: string };
  if (typeof body.magic_link_url !== "string" || body.magic_link_url.length > 2048) {
    throw new Error("magic_link_url missing or invalid");
  }
  const cb = await fetch(body.magic_link_url, { redirect: "manual" });
  if (cb.status !== 302) {
    throw new Error(`callback expected 302, got ${cb.status}`);
  }
  const rawCookie = cb.headers.get("set-cookie");
  if (rawCookie === null || rawCookie.length === 0) {
    throw new Error("no Set-Cookie on callback response");
  }
  const m = /wf_session=([^;]+)/.exec(rawCookie);
  if (m === null) {
    throw new Error("wf_session cookie not found in Set-Cookie");
  }
  const sessionVal = m[1] ?? "";
  if (sessionVal.length === 0 || sessionVal.length > 512) {
    throw new Error("session cookie value exceeds maximum length");
  }

  const authDir = path.join(process.cwd(), "e2e", ".auth");
  fs.mkdirSync(authDir, { recursive: true });
  const exp = Math.floor(Date.now() / 1000) + 30 * 24 * 3600;
  fs.writeFileSync(
    path.join(authDir, "storage.json"),
    JSON.stringify({
      cookies: [
        {
          name: "wf_session",
          value: sessionVal,
          domain: "127.0.0.1",
          path: "/",
          expires: exp,
          httpOnly: true,
          secure: false,
          sameSite: "Lax",
        },
      ],
      origins: [],
    }),
  );
  fs.writeFileSync(
    path.join(authDir, "fixture.json"),
    JSON.stringify({ case_id: parsed.case_id, api_url: api }),
  );
};

export default globalSetup;
