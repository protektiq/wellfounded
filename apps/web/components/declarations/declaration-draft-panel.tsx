"use client";

import type { ReactNode } from "react";

import { flagSpanClass } from "@/components/declarations/flag-styles";
import type {
  DeclarationDraftContent,
  DeclarationFlag,
} from "@/lib/declaration-schemas";
import { SECTION_LABELS, SECTION_ORDER } from "@/lib/declaration-schemas";
import { cn } from "@/lib/utils";

type DeclarationDraftPanelProps = {
  draft: DeclarationDraftContent;
  flags: DeclarationFlag[];
  activeFlagId: string | null;
  onFlagClick: (flagId: string) => void;
};

const renderParagraphWithFlags = (
  text: string,
  paragraphId: string,
  flags: DeclarationFlag[],
  activeFlagId: string | null,
  onFlagClick: (flagId: string) => void,
): ReactNode[] => {
  const openFlags = flags.filter(
    (f) => f.paragraph_id === paragraphId && f.status === "open",
  );
  if (openFlags.length === 0) {
    return [<span key="plain">{text}</span>];
  }

  const boundaries = new Set<number>([0, text.length]);
  for (const f of openFlags) {
    boundaries.add(f.span.start);
    boundaries.add(f.span.end);
  }
  const points = [...boundaries].sort((a, b) => a - b);
  const nodes: ReactNode[] = [];
  let key = 0;

  for (let i = 0; i < points.length - 1; i += 1) {
    const start = points[i] ?? 0;
    const end = points[i + 1] ?? text.length;
    if (start >= end) {
      continue;
    }
    const chunk = text.slice(start, end);
    const covering = openFlags.filter(
      (f) => f.span.start <= start && f.span.end >= end,
    );
    if (covering.length === 0) {
      nodes.push(<span key={`t-${key++}`}>{chunk}</span>);
      continue;
    }
    const primary = covering[0];
    if (primary === undefined) {
      nodes.push(<span key={`t-${key++}`}>{chunk}</span>);
      continue;
    }
    nodes.push(
      <button
        key={`f-${key++}`}
        type="button"
        className={cn(
          "cursor-pointer rounded-sm px-0.5 text-left",
          flagSpanClass(primary.type),
          activeFlagId === primary.id && "ring-2 ring-[var(--oxblood)]",
        )}
        onClick={() => onFlagClick(primary.id)}
        aria-label={`Open flag: ${primary.type}`}
      >
        {chunk}
      </button>,
    );
  }
  return nodes;
};

export const DeclarationDraftPanel = ({
  draft,
  flags,
  activeFlagId,
  onFlagClick,
}: DeclarationDraftPanelProps) => {
  return (
    <div className="space-y-8">
      {SECTION_ORDER.map((sectionId) => {
        const section = draft.sections[sectionId];
        if (section === undefined) {
          return null;
        }
        const title = SECTION_LABELS[sectionId] ?? sectionId;
        return (
          <section key={sectionId} aria-labelledby={`section-${sectionId}`}>
            <h3
              id={`section-${sectionId}`}
              className="mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground"
            >
              {title}
            </h3>
            <div className="space-y-4">
              {section.paragraphs.map((para) => (
                <p
                  key={para.id}
                  className="text-base leading-relaxed text-foreground"
                  data-paragraph-id={para.id}
                >
                  {renderParagraphWithFlags(
                    para.text,
                    para.id,
                    flags,
                    activeFlagId,
                    onFlagClick,
                  )}
                </p>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
};
