"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getApiBaseUrl } from "@/lib/api-base";

type MePayload = {
  user: { role: string };
  mfa_verified: boolean;
  webauthn_credential_count: number;
};

export default function OrgAdminUsersPage() {
  const router = useRouter();
  const [state, setState] = useState<"loading" | "ready" | "forbidden" | "error">("loading");
  const [payload, setPayload] = useState<unknown>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      try {
        const api = getApiBaseUrl();
        const meRes = await fetch(`${api}/auth/me`, { credentials: "include" });
        if (meRes.status === 401) {
          router.replace("/");
          return;
        }
        if (!meRes.ok) {
          setState("error");
          setErrorDetail(`Session lookup failed (${meRes.status})`);
          return;
        }
        const me = (await meRes.json()) as MePayload;
        if (me.user.role !== "admin") {
          setState("forbidden");
          return;
        }
        if (me.webauthn_credential_count === 0) {
          router.replace("/auth/webauthn/register");
          return;
        }
        if (!me.mfa_verified) {
          router.replace("/auth/webauthn/authenticate");
          return;
        }
        const usersRes = await fetch(`${api}/orgs/admin/users`, { credentials: "include" });
        if (usersRes.status === 403) {
          router.replace("/auth/webauthn/authenticate");
          return;
        }
        if (!usersRes.ok) {
          setState("error");
          setErrorDetail(`Users request failed (${usersRes.status})`);
          return;
        }
        setPayload(await usersRes.json());
        setState("ready");
      } catch (e) {
        setState("error");
        setErrorDetail(e instanceof Error ? e.message : "Unexpected error");
      }
    };
    void run();
  }, [router]);

  if (state === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Loading</p>
      </div>
    );
  }

  if (state === "forbidden") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 dark:bg-zinc-950">
        <p className="text-center text-sm text-zinc-700 dark:text-zinc-300">
          You do not have access to this page.
        </p>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 dark:bg-zinc-950">
        <p className="text-center text-sm text-red-600 dark:text-red-400" role="alert">
          {errorDetail ?? "Error"}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 bg-zinc-50 px-4 py-10 dark:bg-zinc-950">
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Organization users</h1>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Stub list (full user management ships in a later milestone).
      </p>
      <pre className="overflow-x-auto rounded-md border border-zinc-200 bg-white p-4 text-xs text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </div>
  );
}
