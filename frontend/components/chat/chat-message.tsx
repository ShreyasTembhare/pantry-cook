"use client";

import { ChatCards } from "@/components/chat/chat-cards";
import { Pip } from "@/components/mascot/pip";
import type { ChatMessage as ChatMessageModel, Item } from "@/lib/api";
import { cn } from "@/lib/utils";

export function ChatMessage({
  message,
  pantry,
  busy,
  openPendingId,
  liveCookCardKey,
  onConfirmPending,
  onCancelPending,
  onRevise,
  onAbandon,
  onAskConfirm,
}: {
  message: ChatMessageModel;
  pantry: Item[];
  busy: boolean;
  openPendingId?: string | null;
  liveCookCardKey?: string | null;
  onConfirmPending: (pendingId: string, acknowledgeExpired: boolean) => void;
  onCancelPending: (pendingId: string) => void;
  onRevise: (note: string) => void;
  onAbandon: () => void;
  onAskConfirm: () => void;
}) {
  const mine = message.role === "user";
  const pending = message.id.startsWith("pending-user-");
  const failed = message.id.startsWith("failed-user-");
  return (
    <div className={cn("flex gap-3", mine ? "justify-end" : "justify-start")}>
      {mine ? null : <Pip mood="happy" className="mt-1 h-10 w-9 shrink-0" />}
      <div className={cn("max-w-[min(100%,36rem)]", mine && "max-w-[min(100%,28rem)]")}>
        <div
          className={cn(
            "rounded-3xl px-4 py-3 text-sm leading-relaxed shadow-sm",
            mine
              ? cn(
                  "rounded-br-lg bg-primary text-primary-foreground",
                  pending && "opacity-80",
                  failed && "opacity-70 ring-2 ring-destructive/60",
                )
              : "rounded-bl-lg border border-border/70 bg-card/90 backdrop-blur",
          )}
        >
          <span className="sr-only">{mine ? "You said: " : "Pip said: "}</span>
          {message.content}
        </div>
        {pending || failed ? (
          <p
            className={cn(
              "mt-1 text-right text-xs",
              failed ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {failed ? "Not sent" : "Sending…"}
          </p>
        ) : null}
        {mine ? null : (
          <ChatCards
            cards={message.cards}
            pantry={pantry}
            busy={busy}
            messageId={message.id}
            openPendingId={openPendingId}
            liveCookCardKey={liveCookCardKey}
            onConfirmPending={onConfirmPending}
            onCancelPending={onCancelPending}
            onRevise={onRevise}
            onAbandon={onAbandon}
            onAskConfirm={onAskConfirm}
          />
        )}
      </div>
    </div>
  );
}
