import { Skeleton } from "@/components/ui/skeleton";

export default function CountryConditionsLoading() {
  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <div className="relative h-[420px] rounded-lg border border-border/80 bg-card/40 p-6">
        <div className="absolute top-6 left-6 right-6 space-y-3">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
        <div className="absolute top-24 left-6 right-10 h-48 rotate-[-1.5deg] rounded-md border border-border/60 bg-background/90 shadow-md" />
        <div className="absolute top-28 left-8 right-14 h-48 rotate-[0.8deg] rounded-md border border-border/50 bg-background/80 shadow-sm" />
        <div className="absolute top-32 left-10 right-8 h-48 rotate-[-0.5deg] rounded-md border border-border/70 bg-card shadow-lg" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-20 w-full rounded-lg" />
        <Skeleton className="h-20 w-full rounded-lg" />
        <Skeleton className="h-20 w-full rounded-lg" />
      </div>
    </div>
  );
}
