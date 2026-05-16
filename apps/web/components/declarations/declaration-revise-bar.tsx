"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getApiBaseUrl } from "@/lib/api-base";
import type { DeclarationDraftContent } from "@/lib/declaration-schemas";
import { SECTION_LABELS, SECTION_ORDER } from "@/lib/declaration-schemas";

type DeclarationReviseBarProps = {
  caseId: string;
  draftId: string;
  draft: DeclarationDraftContent;
};

type ScopeOption = {
  value: string;
  label: string;
  scope: { paragraph_id?: string; section_id?: string };
};

export const DeclarationReviseBar = ({
  caseId,
  draftId,
  draft,
}: DeclarationReviseBarProps) => {
  const router = useRouter();
  const [instruction, setInstruction] = useState("");
  const [scopeValue, setScopeValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const scopeOptions = useMemo((): ScopeOption[] => {
    const opts: ScopeOption[] = [];
    for (const sectionId of SECTION_ORDER) {
      const section = draft.sections[sectionId];
      if (section === undefined) {
        continue;
      }
      const sectionLabel = SECTION_LABELS[sectionId] ?? sectionId;
      opts.push({
        value: `section:${sectionId}`,
        label: `Section: ${sectionLabel}`,
        scope: { section_id: sectionId },
      });
      for (const para of section.paragraphs) {
        opts.push({
          value: `para:${para.id}`,
          label: `Paragraph: ${para.id}`,
          scope: { paragraph_id: para.id },
        });
      }
    }
    return opts;
  }, [draft]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const trimmed = instruction.trim();
    if (trimmed.length === 0) {
      setError("Enter a revision instruction.");
      return;
    }
    const selected = scopeOptions.find((o) => o.value === scopeValue);
    if (selected === undefined) {
      setError("Select a target scope.");
      return;
    }
    setPending(true);
    const r = await fetch(
      `${getApiBaseUrl()}/cases/${caseId}/declarations/${draftId}/revise`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction: trimmed,
          scope: selected.scope,
        }),
      },
    );
    setPending(false);
    if (r.status === 401) {
      window.location.href = "/";
      return;
    }
    if (!r.ok) {
      setError("Revision request failed.");
      return;
    }
    const body = (await r.json()) as { draft_id?: string };
    if (typeof body.draft_id === "string") {
      router.push(`/cases/${caseId}/declarations/${body.draft_id}`);
      router.refresh();
    }
  };

  return (
    <form
      onSubmit={(e) => void handleSubmit(e)}
      className="rounded-lg border border-border/80 bg-card/50 p-4"
    >
      <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
        Revision
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Label htmlFor="revise-instruction">Instruction</Label>
          <Textarea
            id="revise-instruction"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            rows={2}
            className="mt-1"
            placeholder="Strengthen the nexus paragraph..."
          />
        </div>
        <div>
          <Label htmlFor="revise-scope">Target scope</Label>
          <select
            id="revise-scope"
            className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs"
            value={scopeValue}
            onChange={(e) => setScopeValue(e.target.value)}
          >
            <option value="">Select paragraph or section</option>
            {scopeOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <Button type="submit" disabled={pending}>
            Request revision
          </Button>
        </div>
      </div>
      {error !== null ? (
        <p className="mt-2 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
};
