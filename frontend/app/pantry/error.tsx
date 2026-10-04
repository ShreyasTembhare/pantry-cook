"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function PantryError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">Pantry hit a snag</h2>
      <p role="alert" className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
        {error.message || "Something went wrong while opening the pantry."}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button type="button" className="h-11 lg:h-9" onClick={reset}>
          Retry
        </Button>
        <Button asChild variant="ghost" className="h-11 lg:h-9">
          <Link href="/">Back to chat</Link>
        </Button>
      </div>
    </div>
  );
}
