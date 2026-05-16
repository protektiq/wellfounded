import { Skeleton } from "@/components/ui/skeleton";

export default function DeclarationsLoading() {
  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <div className="relative h-[420px] rounded-lg border border-border/80 bg-card/40 p-6">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="mt-4 h-10 w-40" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-20 w-full rounded-lg" />
        <Skeleton className="h-20 w-full rounded-lg" />
      </div>
    </div>
  );
}
