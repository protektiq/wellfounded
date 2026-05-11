"use client";

import { startRegistration } from "@simplewebauthn/browser";
import { useState } from "react";

import { getApiBaseUrl } from "@/lib/api-base";

const _friendlyName = "Admin passkey";

export default function WebAuthnRegisterPage() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRegister = async () => {
    setError(null);
    setMessage(null);
    try {
      const api = getApiBaseUrl();
      const begin = await fetch(`${api}/auth/webauthn/register/begin`, {
        method: "POST",
        credentials: "include",
      });
      if (!begin.ok) {
        setError(`Registration begin failed (${begin.status})`);
        return;
      }
      const options = (await begin.json()) as Parameters<
        typeof startRegistration
      >[0]["optionsJSON"];
      const attestation = await startRegistration({ optionsJSON: options });
      const finish = await fetch(`${api}/auth/webauthn/register/finish`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          friendly_name: _friendlyName,
          credential: attestation,
        }),
      });
      if (!finish.ok) {
        setError(`Registration finish failed (${finish.status})`);
        return;
      }
      setMessage("Passkey registered. You can return to the admin area.");
    } catch (e) {
      const text = e instanceof Error ? e.message : "Unexpected error";
      setError(text);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-50 px-4 dark:bg-zinc-950">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Register admin passkey
        </h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          Complete WebAuthn enrollment for your administrator account.
        </p>
      </div>
      <button
        type="button"
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200 dark:focus-visible:outline-zinc-100"
        onClick={() => void handleRegister()}
        aria-label="Start passkey registration"
      >
        Register passkey
      </button>
      {error !== null ? (
        <p className="max-w-md text-center text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      ) : null}
      {message !== null ? (
        <p className="max-w-md text-center text-sm text-green-800 dark:text-green-300">{message}</p>
      ) : null}
    </div>
  );
}
