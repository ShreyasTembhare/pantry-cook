"use client";

import Link from "next/link";

import { ProposalCard, type PantryAmount } from "@/components/cook/proposal-card";
import { ChatPendingCard } from "@/components/chat/chat-pending-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { ChatCard, Item } from "@/lib/api";
import { cookErrorPresentation } from "@/lib/cook";
import { formatExpiry, localISODate, urgencyOf } from "@/lib/pantry";

function pantryMap(items: Item[]): Record<string, PantryAmount> {
  return Object.fromEntries(
    items.map((item) => [
      item.id,
      {
        name: item.name,
        quantity: item.quantity,
        unit: item.unit,
        expires_on: item.expires_on,
      },
    ]),
  );
}

export function ChatCards({
  cards,
  pantry,
  busy,
  messageId,
  openPendingId,
  liveCookCardKey,
  onConfirmPending,
  onCancelPending,
  onRevise,
  onAbandon,
  onAskConfirm,
}: {
  cards: ChatCard[];
  pantry: Item[];
  busy: boolean;
  messageId?: string;
  /** Id of the confirmation still waiting, or null. Leave out to treat every card as live. */
  openPendingId?: string | null;
  /**
   * `${messageId}:${index}` of the recipe that can still be cooked.
   * Leave out to keep every recipe actionable. Null means none of them are.
   */
  liveCookCardKey?: string | null;
  onConfirmPending: (pendingId: string, acknowledgeExpired: boolean) => void;
  onCancelPending: (pendingId: string) => void;
  onRevise: (note: string) => void;
  onAbandon: () => void;
  onAskConfirm: () => void;
}) {
  if (cards.length === 0) return null;
  const amounts = pantryMap(pantry);

  return (
    <div className="mt-3 flex flex-col gap-3">
      {cards.map((card, index) => {
        const key = card.pending_id ?? `${card.type}-${index}`;
        // Only the newest confirmation can still be answered. Older ones were
        // answered or replaced, so they read as history instead of live buttons.
        if (
          card.type === "pending" &&
          card.pending_id &&
          openPendingId !== undefined &&
          card.pending_id !== openPendingId
        ) {
          return (
            <p key={key} className="text-sm text-muted-foreground">
              {card.title} Already answered.
            </p>
          );
        }
        if (card.type === "pantry") {
          const today = localISODate(new Date());
          return (
            <Card key={key} className="gap-3 rounded-2xl py-4 shadow-sm">
              <CardHeader className="px-4">
                <CardTitle className="text-sm">{card.title}</CardTitle>
              </CardHeader>
              {card.items.length > 0 ? (
                <CardContent className="px-4">
                  <ul className="space-y-2 text-sm text-muted-foreground">
                    {card.items.map((item, itemIndex) => {
                      const urgency = urgencyOf(item, today);
                      return (
                        <li key={item.id}>
                          {itemIndex > 0 ? <Separator className="mb-2" /> : null}
                          <span className="flex items-center justify-between gap-3">
                            <span>
                              {item.name}{" "}
                              <span className="tabular-nums">
                                {item.quantity} {item.unit}
                              </span>
                            </span>
                            {item.expires_on ? (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Badge
                                      variant="outline"
                                      className={
                                        urgency === "expired"
                                          ? "border-transparent bg-expired/10 text-expired"
                                          : urgency === "soon"
                                            ? "border-transparent bg-warning/25 text-warning-foreground"
                                            : undefined
                                      }
                                    >
                                      {urgency === "expired" ? "Expired" : formatExpiry(item.expires_on, today)}
                                    </Badge>
                                  </TooltipTrigger>
                                  <TooltipContent>{formatExpiry(item.expires_on, today)}</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            ) : null}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </CardContent>
              ) : null}
              <CardContent className="px-4">
                <Link href="/pantry" className="text-xs font-medium text-primary">
                  Open pantry
                </Link>
              </CardContent>
            </Card>
          );
        }

        if (card.type === "meals") {
          return (
            <Card key={key} className="gap-3 rounded-2xl py-4 shadow-sm">
              <CardHeader className="px-4">
                <CardTitle className="text-sm">{card.title}</CardTitle>
              </CardHeader>
              {card.meals.length > 0 ? (
                <CardContent className="px-4">
                  <ul className="space-y-1 text-sm">
                    {card.meals.map((meal) => (
                      <li key={meal.id}>
                        <Link href={`/meals/${meal.id}`} className="text-primary">
                          {meal.title}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              ) : null}
            </Card>
          );
        }

        if (card.type === "meal" && card.meal) {
          return (
            <Card key={key} className="gap-2 rounded-2xl py-4 shadow-sm">
              <CardHeader className="px-4">
                <CardTitle className="text-sm">{card.title}</CardTitle>
              </CardHeader>
              <CardContent className="px-4">
                <Link href={`/meals/${card.meal.id}`} className="text-xs font-medium text-primary">
                  Open meal
                </Link>
              </CardContent>
            </Card>
          );
        }

        if (card.type === "error") {
          const shown = cookErrorPresentation(card.error?.code, card.error?.detail ?? card.title);
          return (
            <Alert key={key} variant="destructive" className="rounded-2xl">
              <AlertTitle>{shown.message}</AlertTitle>
              {card.error?.code === "empty_pantry" ? (
                <AlertDescription>
                  <Link href="/pantry" className="font-medium underline">
                    Add items
                  </Link>
                </AlertDescription>
              ) : null}
            </Alert>
          );
        }

        if (card.type === "note") {
          return (
            <p key={key} className="text-sm text-muted-foreground">
              {card.title}
            </p>
          );
        }

        const proposal = card.proposal;
        if ((card.type === "proposal" || card.pending_kind === "confirm_cook") && proposal) {
          const pendingId = card.pending_id;
          const cardKey = `${messageId ?? ""}:${index}`;
          const actionsLive = liveCookCardKey === undefined || liveCookCardKey === cardKey;
          return (
            <ProposalCard
              key={key}
              proposal={proposal}
              pantry={amounts}
              busy={busy}
              showActions={actionsLive}
              pinActions={false}
              onConfirm={(acknowledgeExpired) => {
                if (pendingId) onConfirmPending(pendingId, acknowledgeExpired);
                else onAskConfirm();
              }}
              onRevise={onRevise}
              onAbandon={onAbandon}
            />
          );
        }

        if (card.type === "pending" && card.pending_id) {
          const pendingId = card.pending_id;
          return (
            <ChatPendingCard
              key={key}
              card={card}
              busy={busy}
              onConfirm={() => onConfirmPending(pendingId, false)}
              onCancel={() => onCancelPending(pendingId)}
            />
          );
        }

        return (
          <p key={key} className="text-sm text-muted-foreground">
            {card.title}
          </p>
        );
      })}
    </div>
  );
}
