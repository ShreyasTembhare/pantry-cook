"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import type { ChatCard } from "@/lib/api";
import { pendingSummary } from "@/lib/chat";

/** One line above the thread: the meal in progress and any answer Pip is waiting on. */
export function ChatStatus({
  cookSessionId,
  pending,
}: {
  cookSessionId: string | null;
  pending: ChatCard | null;
}) {
  if (!cookSessionId && !pending) return null;
  return (
    <div
      role="status"
      aria-label="Conversation status"
      className="shrink-0 border-b border-border/70 bg-card/80 backdrop-blur"
    >
      <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 text-xs sm:px-6">
        {cookSessionId ? (
          <span className="flex items-center gap-2">
            <Badge variant="secondary">Meal in progress</Badge>
            <Link href={`/cook/${cookSessionId}`} className="font-medium text-primary">
              Open in Cook
            </Link>
          </span>
        ) : null}
        {pending ? (
          <span className="flex items-center gap-2 text-muted-foreground">
            <Badge variant="outline">Waiting for you</Badge>
            <span>{pendingSummary(pending)} Say yes or no.</span>
          </span>
        ) : null}
      </div>
    </div>
  );
}
