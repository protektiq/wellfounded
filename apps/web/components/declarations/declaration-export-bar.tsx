"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { getApiBaseUrl } from "@/lib/api-base";
import { unresolvedRequiredFlagIds } from "@/lib/declaration-schemas";
import type { DeclarationFlag } from "@/lib/declaration-schemas";

type DeclarationExportBarProps = {
  caseId: string;
  draftId: string;
  version: number;
  flags: DeclarationFlag[];
};

export const DeclarationExportBar = ({
  caseId,
  draftId,
  version,
  flags,
}: DeclarationExportBarProps) => {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const blocked = unresolvedRequiredFlagIds(flags);
  const cleanDisabled = blocked.length > 0;

  const download = async (mode: "working" | "clean", parallel: boolean) => {
    const key = parallel ? "parallel" : mode;
    setPending(key);
    setError(null);
    const params = new URLSearchParams({ mode });
    if (parallel) {
      params.set("parallel", "true");
    }
    const r = await fetch(
      `${getApiBaseUrl()}/cases/${caseId}/declarations/${draftId}/export.docx?${params.toString()}`,
      { credentials: "include" },
    );
    setPending(null);
    if (r.status === 401) {
      window.location.href = "/";
      return;
    }
    if (r.status === 409) {
      setError("Clean export blocked: resolve required flags first.");
      return;
    }
    if (!r.ok) {
      setError("Export failed.");
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `declaration-v${String(version)}-${parallel ? "parallel" : mode}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="rounded-lg border border-border/80 bg-card/50 p-4">
      <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
        Export
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={pending !== null}
          onClick={() => void download("working", false)}
        >
          Working copy
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={pending !== null || cleanDisabled}
          title={
            cleanDisabled
              ? `${String(blocked.length)} required flag(s) still open`
              : undefined
          }
          onClick={() => void download("clean", false)}
        >
          Clean copy
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={pending !== null}
          onClick={() => void download("working", true)}
        >
          Parallel (bilingual)
        </Button>
      </div>
      {cleanDisabled ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Clean export is unavailable until all GAP, INFERENCE, and INCONSISTENCY flags
          are resolved or deferred.
        </p>
      ) : null}
      {error !== null ? (
        <p className="mt-2 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
};
