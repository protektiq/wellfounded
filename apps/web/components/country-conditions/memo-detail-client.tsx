"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { getApiBaseUrl } from "@/lib/api-base";
import { cn } from "@/lib/utils";
import type {
  CitedPassagePayload,
  CountryConditionsMemoDetail,
  FinalMemoOutput,
} from "@/lib/cc-schemas";

const _CITE_RE =
  /<cite\s+passage_id="([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"\s*\/>/g;

const MemoStatusPoller = ({
  active,
}: {
  active: boolean;
}) => {
  const router = useRouter();
  useEffect(() => {
    if (!active) {
      return;
    }
    const t = setInterval(() => {
      router.refresh();
    }, 2000);
    return () => clearInterval(t);
  }, [active, router]);
  return null;
};

const renderProseWithCites = (
  body: string,
  labelByPassageId: Map<string, number>,
  onCiteClick: (passageId: string) => void,
): ReactNode[] => {
  const nodes: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(_CITE_RE.source, "g");
  let key = 0;
  while ((m = re.exec(body)) !== null) {
    if (m.index > last) {
      nodes.push(
        <span key={`t-${key++}`}>{body.slice(last, m.index)}</span>,
      );
    }
    const pid = m[1] ?? "";
    const label = labelByPassageId.get(pid);
    nodes.push(
      <sup key={`c-${key++}`} className="mx-0.5">
        <button
          type="button"
          className="cursor-pointer rounded-sm border border-transparent px-0.5 font-medium text-[var(--oxblood)] underline decoration-[var(--oxblood)]/50 underline-offset-2 hover:bg-[var(--oxblood)]/10 focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={
            label !== undefined
              ? `Open source for citation ${String(label)}`
              : "Open cited source"
          }
          onClick={() => onCiteClick(pid)}
        >
          {label !== undefined ? String(label) : "?"}
        </button>
      </sup>,
    );
    last = m.index + m[0].length;
  }
  if (last < body.length) {
    nodes.push(<span key={`t-${key++}`}>{body.slice(last)}</span>);
  }
  return nodes;
};

type MemoDetailClientProps = {
  caseId: string;
  memoId: string;
  memo: CountryConditionsMemoDetail;
  finalMemo: FinalMemoOutput | null;
};

export const MemoDetailClient = ({
  caseId,
  memoId,
  memo,
  finalMemo,
}: MemoDetailClientProps) => {
  const router = useRouter();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [activePassageId, setActivePassageId] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const passageById = useMemo(() => {
    const m = new Map<string, CitedPassagePayload>();
    for (const p of memo.cited_passages) {
      m.set(p.passage_id, p);
    }
    return m;
  }, [memo.cited_passages]);

  const labelByPassageId = useMemo(() => {
    const ord = new Map<string, number>();
    let i = 1;
    for (const p of memo.cited_passages) {
      if (!ord.has(p.passage_id)) {
        ord.set(p.passage_id, i);
        i += 1;
      }
    }
    return ord;
  }, [memo.cited_passages]);

  const activePassage =
    activePassageId !== null ? passageById.get(activePassageId) : undefined;

  const handleOpenCitation = useCallback((passageId: string) => {
    setActivePassageId(passageId);
    setSheetOpen(true);
  }, []);

  const handleExportDocx = async () => {
    setExportError(null);
    try {
      const res = await fetch(
        `${getApiBaseUrl()}/cases/${caseId}/country-conditions/${memoId}/export.docx`,
        { credentials: "include" },
      );
      if (res.status === 401) {
        router.replace("/");
        return;
      }
      if (!res.ok) {
        setExportError(`Export failed (${res.status}).`);
        return;
      }
      const cd = res.headers.get("Content-Disposition");
      let filename = "country_conditions.docx";
      if (cd !== null && cd.includes("filename=")) {
        const raw = cd.split("filename=")[1]?.trim();
        if (raw !== undefined) {
          filename = raw.replace(/^"|"$/g, "");
        }
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setExportError("Network error during export.");
    }
  };

  const handleRetry = async () => {
    setRetryError(null);
    const i = memo.inputs;
    const body = {
      country_code: i.country_code,
      basis: i.basis,
      group_description: i.group_description,
      timeframe_start_year: i.timeframe_start_year,
      jurisdiction_asylum_office: i.jurisdiction_asylum_office,
    };
    setRetrying(true);
    try {
      const res = await fetch(
        `${getApiBaseUrl()}/cases/${caseId}/country-conditions`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (res.status === 401) {
        router.replace("/");
        return;
      }
      if (res.status !== 202) {
        setRetryError(`Retry failed (${res.status}).`);
        return;
      }
      const j = (await res.json()) as { memo_id?: string };
      if (typeof j.memo_id !== "string") {
        setRetryError("Unexpected response from server.");
        return;
      }
      router.push(`/cases/${caseId}/country-conditions/${j.memo_id}`);
      router.refresh();
    } catch {
      setRetryError("Network error. Try again.");
    } finally {
      setRetrying(false);
    }
  };

  if (memo.status === "pending" || memo.status === "generating") {
    return (
      <div className="space-y-4">
        <MemoStatusPoller active />
        <p className="text-sm text-muted-foreground">
          {memo.status === "pending"
            ? "Generation is queued. This page refreshes automatically."
            : "Drafting and verifying citations. This page refreshes automatically."}
        </p>
        <div className="space-y-3 rounded-lg border border-border/80 bg-card/50 p-6">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
        </div>
      </div>
    );
  }

  if (memo.status === "failed") {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6">
        <h2 className="text-lg font-medium text-destructive">Generation failed</h2>
        <p className="mt-2 text-sm text-foreground">
          {memo.error_message ?? "An unknown error occurred."}
        </p>
        {retryError !== null ? (
          <p className="mt-2 text-sm text-destructive" role="alert">
            {retryError}
          </p>
        ) : null}
        <Button
          type="button"
          className="mt-4"
          variant="secondary"
          disabled={retrying}
          onClick={() => void handleRetry()}
        >
          {retrying ? "Retrying" : "Retry"}
        </Button>
      </div>
    );
  }

  if (finalMemo === null) {
    return (
      <p className="text-sm text-muted-foreground">
        Memo output is not available in a readable form.
      </p>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="default" onClick={() => void handleExportDocx()}>
          Export DOCX
        </Button>
        {exportError !== null ? (
          <span className="text-sm text-destructive" role="alert">
            {exportError}
          </span>
        ) : null}
        <Link
          href={`/cases/${caseId}/country-conditions?fromMemo=${memoId}`}
          className={cn(
            buttonVariants({ variant: "outline", size: "default" }),
            "inline-flex no-underline",
          )}
        >
          Generate new version
        </Link>
      </div>

      <article className="space-y-10">
        {finalMemo.sections.map((sec) => (
          <section key={sec.section_id} className="scroll-mt-8">
            <h2
              className="mb-3 text-xl font-medium tracking-tight text-foreground"
              style={{
                fontFamily: "var(--font-display), ui-serif, Georgia, serif",
              }}
            >
              {sec.title}
            </h2>
            <div className="max-w-none text-base leading-relaxed text-foreground">
              {renderProseWithCites(sec.body, labelByPassageId, handleOpenCitation)}
            </div>
          </section>
        ))}
      </article>

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right" className="w-full sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>Cited source</SheetTitle>
            <SheetDescription>
              Passage as retrieved from the source library.
            </SheetDescription>
          </SheetHeader>
          {activePassage !== undefined ? (
            <ScrollArea className="mt-4 h-[calc(100vh-10rem)] pr-4">
              <dl className="space-y-2 text-sm">
                <div>
                  <dt className="font-medium text-muted-foreground">Document</dt>
                  <dd>{activePassage.document_title}</dd>
                </div>
                <div>
                  <dt className="font-medium text-muted-foreground">Published</dt>
                  <dd>{activePassage.publication_date}</dd>
                </div>
                <div>
                  <dt className="font-medium text-muted-foreground">Source family</dt>
                  <dd className="break-all">{activePassage.source_family}</dd>
                </div>
                <div>
                  <dt className="font-medium text-muted-foreground">URL</dt>
                  <dd>
                    <a
                      href={activePassage.url}
                      className="break-all text-[var(--oxblood)] underline"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {activePassage.url}
                    </a>
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-muted-foreground">Section anchor</dt>
                  <dd>{activePassage.section_anchor}</dd>
                </div>
              </dl>
              <p className="mt-6 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                {activePassage.text}
              </p>
            </ScrollArea>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">
              Citation metadata is not available for this passage.
            </p>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
};
