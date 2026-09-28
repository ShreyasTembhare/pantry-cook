import { Skeleton } from "@/components/ui/skeleton";

export function PantrySkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading pantry" className="divide-y divide-border">
      {Array.from({ length: 6 }, (_, index) => (
        <div
          key={index}
          className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-3 sm:grid-cols-[minmax(0,1.4fr)_7rem_8rem_2.75rem]"
        >
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-4 w-14 justify-self-end" />
          <Skeleton className="col-start-1 h-3 w-24 sm:col-start-auto" />
          <Skeleton className="size-8 justify-self-end rounded-md" />
        </div>
      ))}
    </div>
  );
}
