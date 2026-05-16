import type { DeclarationFlag } from "@/lib/declaration-schemas";
import { cn } from "@/lib/utils";

export const flagTypeLabel = (type: DeclarationFlag["type"]): string => {
  return type.replaceAll("_", " ");
};

export const flagSpanClass = (type: DeclarationFlag["type"]): string => {
  if (type === "GAP" || type === "INCONSISTENCY") {
    return "bg-destructive/15 underline decoration-destructive/60";
  }
  if (type === "INFERENCE") {
    return "bg-amber-500/20 underline decoration-amber-600/50";
  }
  return "underline decoration-muted-foreground/60";
};

export const flagBadgeClass = (type: DeclarationFlag["type"]): string => {
  return cn(
    "text-[10px] font-semibold uppercase tracking-wide",
    type === "GAP" || type === "INCONSISTENCY"
      ? "text-destructive"
      : type === "INFERENCE"
        ? "text-amber-800 dark:text-amber-200"
        : "text-muted-foreground",
  );
};
