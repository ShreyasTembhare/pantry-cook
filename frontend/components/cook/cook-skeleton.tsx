import { Skeleton } from "@/components/ui/skeleton";

export function CookStartSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading cook" className="space-y-4">
      <Skeleton className="h-32 w-full rounded-md" />
      <div className="flex gap-2">
        <Skeleton className="h-9 w-40 rounded-md" />
        <Skeleton className="h-9 w-36 rounded-md" />
      </div>
      <Skeleton className="h-11 w-28 rounded-md" />
    </div>
  );
}

export function ProposalSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Loading proposal"
      className="rounded-lg border border-border px-4 py-5 sm:px-5"
    >
      <Skeleton className="h-7 w-56" />
      <Skeleton className="mt-3 h-4 w-24" />
      <Skeleton className="mt-6 h-3 w-16" />
      <Skeleton className="mt-3 h-4 w-full" />
      <Skeleton className="mt-3 h-4 w-4/5" />
      <Skeleton className="mt-6 h-3 w-16" />
      <Skeleton className="mt-3 h-4 w-full" />
      <Skeleton className="mt-2 h-4 w-11/12" />
      <Skeleton className="mt-2 h-4 w-3/4" />
    </div>
  );
}

export function MealsSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading meals" className="divide-y divide-border">
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index} className="flex items-center justify-between gap-4 py-4">
          <div className="space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-28" />
          </div>
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  );
}
