import { Suspense } from "react";

import { CookStart } from "@/components/cook/cook-start";
import { CookStartSkeleton } from "@/components/cook/cook-skeleton";

export const metadata = {
  title: "Cook · Pantry Cook",
};

export default function CookPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
          <CookStartSkeleton />
        </div>
      }
    >
      <CookStart />
    </Suspense>
  );
}
