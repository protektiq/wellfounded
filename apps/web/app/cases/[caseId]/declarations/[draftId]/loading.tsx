import { Skeleton } from "@/components/ui/skeleton";

export default function DeclarationDetailLoading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-24 w-full" />
      <div className="grid gap-8 lg:grid-cols-5">
        <Skeleton className="h-96 lg:col-span-3" />
        <Skeleton className="h-96 lg:col-span-2" />
      </div>
      <Skeleton className="h-20 w-full" />
    </div>
  );
}
