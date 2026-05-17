"use client";

import { flagBadgeClass, flagTypeLabel } from "@/components/declarations/flag-styles";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { DeclarationFlag } from "@/lib/declaration-schemas";
import { cn } from "@/lib/utils";

type DeclarationFlagPanelProps = {
  flags: DeclarationFlag[];
  activeFlagId: string | null;
  onSelectFlag: (flagId: string) => void;
  onEditFlag: (flag: DeclarationFlag) => void;
  onResolveQuick: (flag: DeclarationFlag) => void;
  onDeferQuick: (flag: DeclarationFlag) => void;
};

export const DeclarationFlagPanel = ({
  flags,
  activeFlagId,
  onSelectFlag,
  onEditFlag,
  onResolveQuick,
  onDeferQuick,
}: DeclarationFlagPanelProps) => {
  const openFlags = flags.filter((f) => f.status === "open");
  const closedFlags = flags.filter((f) => f.status !== "open");

  return (
    <div className="flex h-full flex-col rounded-lg border border-border/80 bg-card/50">
      <div className="border-b border-border/60 px-4 py-3">
        <h2
          className="text-sm font-medium text-foreground"
          style={{
            fontFamily: "var(--font-display), ui-serif, Georgia, serif",
          }}
        >
          Flags
        </h2>
        <p className="text-xs text-muted-foreground">
          {openFlags.length} open, {closedFlags.length} resolved or deferred
        </p>
      </div>
      <ScrollArea className="flex-1 px-4 py-3">
        {openFlags.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No open flags. Clean export is available when required flags are
            resolved or deferred.
          </p>
        ) : (
          <ul className="space-y-3">
            {openFlags.map((flag) => (
              <li
                key={flag.id}
                className={cn(
                  "rounded-md border border-border/70 p-3 transition-colors",
                  activeFlagId === flag.id && "border-[var(--oxblood)]/50 bg-[var(--oxblood)]/5",
                )}
              >
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={() => onSelectFlag(flag.id)}
                >
                  <span className={flagBadgeClass(flag.type)}>
                    {flagTypeLabel(flag.type)}
                  </span>
                  <p className="mt-1 text-sm text-foreground">{flag.description}</p>
                </button>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => onResolveQuick(flag)}
                  >
                    Accept
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => onDeferQuick(flag)}
                  >
                    Defer
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => onEditFlag(flag)}
                  >
                    Edit
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </ScrollArea>
    </div>
  );
};
