"use client";

import { useEffect, useState } from "react";

import { flagBadgeClass, flagTypeLabel } from "@/components/declarations/flag-styles";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { getApiBaseUrl } from "@/lib/api-base";
import type { DeclarationFlag, TranscriptDetail } from "@/lib/declaration-schemas";

type FlagResolutionDrawerProps = {
  caseId: string;
  draftId: string;
  flag: DeclarationFlag | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  transcript: TranscriptDetail | null;
  onApplied: () => void;
  onPlaySegment?: (start: number, end: number) => void;
};

const firstSegment = (
  transcript: TranscriptDetail | null,
): { start: number; end: number } | null => {
  const segments = transcript?.segments;
  if (segments === null || segments === undefined || segments.length === 0) {
    return null;
  }
  const seg = segments[0];
  if (seg === undefined) {
    return null;
  }
  return { start: seg.start, end: seg.end };
};

export const FlagResolutionDrawer = ({
  caseId,
  draftId,
  flag,
  open,
  onOpenChange,
  transcript,
  onApplied,
  onPlaySegment,
}: FlagResolutionDrawerProps) => {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [text, setText] = useState("");
  const [rejectNote, setRejectNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (flag !== null) {
      setText(flag.suggested_resolution);
      setRejectNote("");
      setMode("view");
      setError(null);
    }
  }, [flag]);

  if (flag === null) {
    return null;
  }

  const seg = firstSegment(transcript);

  const postApply = async (body: {
    resolution_text: string;
    status: "resolved" | "deferred";
  }) => {
    setPending(true);
    setError(null);
    const r = await fetch(
      `${getApiBaseUrl()}/cases/${caseId}/declarations/${draftId}/flags/${flag.id}/apply`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    setPending(false);
    if (r.status === 401) {
      window.location.href = "/";
      return;
    }
    if (!r.ok) {
      const t = await r.text();
      setError(t.slice(0, 500) || "Could not apply resolution.");
      return;
    }
    onOpenChange(false);
    onApplied();
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className={flagBadgeClass(flag.type)}>
            {flagTypeLabel(flag.type)}
          </SheetTitle>
          <SheetDescription>{flag.description}</SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-6">
          {flag.transcript_quote !== null ? (
            <div>
              <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                Interview transcript
              </p>
              <p className="mt-2 text-sm italic text-foreground">
                &ldquo;{flag.transcript_quote}&rdquo;
              </p>
              {seg !== null && onPlaySegment !== undefined ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() => onPlaySegment(seg.start, seg.end)}
                >
                  Play segment
                </Button>
              ) : null}
            </div>
          ) : null}

          {flag.prior_quote !== null ? (
            <div>
              <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                Prior statement
              </p>
              <p className="mt-2 text-sm italic text-foreground">
                &ldquo;{flag.prior_quote}&rdquo;
              </p>
            </div>
          ) : null}

          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              Suggested resolution
            </p>
            {mode === "edit" ? (
              <Textarea
                className="mt-2"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={5}
                aria-label="Edited resolution text"
              />
            ) : (
              <p className="mt-2 text-sm text-foreground">{flag.suggested_resolution}</p>
            )}
          </div>

          {mode === "reject" ? (
            <div>
              <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                Deferral note
              </p>
              <Textarea
                className="mt-2"
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
                rows={3}
                aria-label="Reason to defer flag"
              />
            </div>
          ) : null}

          {error !== null ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {mode === "view" ? (
              <>
                <Button
                  type="button"
                  onClick={() =>
                    void postApply({
                      resolution_text: flag.suggested_resolution,
                      status: "resolved",
                    })
                  }
                  disabled={pending}
                >
                  Accept
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setMode("edit")}
                  disabled={pending}
                >
                  Edit
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setMode("reject")}
                  disabled={pending}
                >
                  Reject
                </Button>
              </>
            ) : null}
            {mode === "edit" ? (
              <>
                <Button
                  type="button"
                  disabled={pending}
                  onClick={() => {
                    const trimmed = text.trim();
                    if (trimmed.length === 0) {
                      setError("Resolution text is required.");
                      return;
                    }
                    void postApply({ resolution_text: trimmed, status: "resolved" });
                  }}
                >
                  Apply edit
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setMode("view")}
                  disabled={pending}
                >
                  Cancel
                </Button>
              </>
            ) : null}
            {mode === "reject" ? (
              <>
                <Button
                  type="button"
                  variant="destructive"
                  disabled={pending}
                  onClick={() => {
                    const trimmed = rejectNote.trim();
                    if (trimmed.length === 0) {
                      setError("Add a note explaining why this flag is deferred.");
                      return;
                    }
                    void postApply({ resolution_text: trimmed, status: "deferred" });
                  }}
                >
                  Defer with note
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setMode("view")}
                  disabled={pending}
                >
                  Cancel
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
};
