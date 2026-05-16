"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { DeclarationDraftPanel } from "@/components/declarations/declaration-draft-panel";
import { DeclarationExportBar } from "@/components/declarations/declaration-export-bar";
import { DeclarationFlagPanel } from "@/components/declarations/declaration-flag-panel";
import { DeclarationReviseBar } from "@/components/declarations/declaration-revise-bar";
import { DeclarationStatusPoller } from "@/components/declarations/declaration-status-poller";
import { FlagResolutionDrawer } from "@/components/declarations/flag-resolution-drawer";
import {
  TranscriptAudioPanel,
  type TranscriptAudioHandle,
} from "@/components/declarations/transcript-audio-panel";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getApiBaseUrl } from "@/lib/api-base";
import type {
  DeclarationDraftDetail,
  DeclarationFlag,
  TranscriptDetail,
} from "@/lib/declaration-schemas";
import {
  statusBadgeVariant,
  statusPillLabel,
} from "@/lib/declaration-schemas";
import { cn } from "@/lib/utils";

type DeclarationDetailClientProps = {
  caseId: string;
  draftId: string;
  detail: DeclarationDraftDetail;
  transcript: TranscriptDetail | null;
};

export const DeclarationDetailClient = ({
  caseId,
  draftId,
  detail,
  transcript,
}: DeclarationDetailClientProps) => {
  const router = useRouter();
  const audioRef = useRef<TranscriptAudioHandle | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeFlagId, setActiveFlagId] = useState<string | null>(null);

  const polling =
    detail.status === "pending" || detail.status === "generating";

  const activeFlag =
    detail.flags.find((f) => f.id === activeFlagId) ?? null;

  const handleRefresh = useCallback(() => {
    router.refresh();
  }, [router]);

  const openFlag = (flagId: string) => {
    setActiveFlagId(flagId);
    setDrawerOpen(true);
  };

  const quickApply = async (
    flag: DeclarationFlag,
    body: { resolution_text: string; status: "resolved" | "deferred" },
  ) => {
    const r = await fetch(
      `${getApiBaseUrl()}/cases/${caseId}/declarations/${draftId}/flags/${flag.id}/apply`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    if (r.ok) {
      handleRefresh();
    }
  };

  if (detail.status === "failed") {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6">
        <h2 className="text-lg font-medium text-destructive">Draft failed</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {detail.error_message ?? "An error occurred during generation."}
        </p>
        <Link
          href={`/cases/${caseId}/declarations/new`}
          className={cn(
            buttonVariants({ variant: "outline" }),
            "mt-4 inline-flex",
          )}
        >
          Start again
        </Link>
      </div>
    );
  }

  if (polling || detail.draft === null) {
    return (
      <>
        <DeclarationStatusPoller active={polling} />
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full" />
          <p className="text-sm text-muted-foreground">Generating declaration draft...</p>
        </div>
      </>
    );
  }

  return (
    <>
      <DeclarationStatusPoller active={false} />
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
            Declaration
          </p>
          <h2
            className="text-xl font-medium text-foreground"
            style={{
              fontFamily: "var(--font-display), ui-serif, Georgia, serif",
            }}
          >
            Version {detail.version}
          </h2>
        </div>
        <Badge variant={statusBadgeVariant(detail.status)}>
          {statusPillLabel(detail.status, detail.finalized_at)}
        </Badge>
      </div>

      <DeclarationReviseBar
        caseId={caseId}
        draftId={draftId}
        draft={detail.draft}
      />

      <div className="mt-6 grid gap-8 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <DeclarationDraftPanel
            draft={detail.draft}
            flags={detail.flags}
            activeFlagId={activeFlagId}
            onFlagClick={openFlag}
          />
        </div>
        <div className="flex flex-col gap-4 lg:col-span-2">
          <DeclarationFlagPanel
            flags={detail.flags}
            activeFlagId={activeFlagId}
            onSelectFlag={openFlag}
            onResolveQuick={(f) =>
              void quickApply(f, {
                resolution_text: f.suggested_resolution,
                status: "resolved",
              })
            }
            onDeferQuick={(f) => openFlag(f.id)}
          />
          <TranscriptAudioPanel
            ref={audioRef}
            caseId={caseId}
            interviewAudioId={detail.interview_audio_id}
            transcript={transcript}
            onSegmentClick={(start, end) =>
              audioRef.current?.playSegment(start, end)
            }
          />
        </div>
      </div>

      <div className="mt-6">
        <DeclarationExportBar
          caseId={caseId}
          draftId={draftId}
          version={detail.version}
          flags={detail.flags}
        />
      </div>

      <FlagResolutionDrawer
        caseId={caseId}
        draftId={draftId}
        flag={activeFlag}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        transcript={transcript}
        onApplied={handleRefresh}
        onPlaySegment={(start, end) =>
          audioRef.current?.playSegment(start, end)
        }
      />
    </>
  );
};
