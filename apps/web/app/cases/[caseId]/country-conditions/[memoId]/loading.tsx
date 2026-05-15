import { Skeleton } from "@/components/ui/skeleton";

export default function CountryConditionsMemoLoading() {
  return (
    <div className="space-y-8">
      <div className="space-y-2 border-b border-border/70 pb-6">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-9 w-2/3 max-w-md" />
      </div>
      <div className="flex gap-3">
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-9 w-44" />
      </div>
      <div className="relative h-[520px] rounded-lg border border-border/80 bg-card/40 p-8">
        <div className="absolute inset-8 space-y-3">
          <Skeleton className="h-6 w-3/5" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-11/12" />
        </div>
        <div className="absolute top-24 right-12 left-12 h-56 rotate-[-1deg] rounded-md border border-border/60 bg-background/95 shadow-md" />
        <div className="absolute top-28 right-10 left-14 h-56 rotate-[0.6deg] rounded-md border border-border/50 bg-background/85 shadow-sm" />
        <div className="absolute top-32 right-8 left-16 h-56 rotate-[-0.3deg] rounded-md border border-border/70 bg-card shadow-lg" />
      </div>
    </div>
  );
}
