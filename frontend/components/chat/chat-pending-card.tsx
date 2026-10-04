"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ChatCard } from "@/lib/api";
import { formatExpiry, localISODate } from "@/lib/pantry";

const COPY = {
  delete_item: {
    confirm: "Remove",
    cancel: "Keep it",
    note: "This takes it out of the pantry for good.",
    destructive: true,
  },
  undo_meal: {
    confirm: "Undo meal",
    cancel: "Keep it",
    note: "The ingredients go back into the pantry.",
    destructive: true,
  },
  confirm_cook: {
    confirm: "Confirm",
    cancel: "Cancel",
    note: "",
    destructive: false,
  },
} as const;

/** A staged delete or undo. Shows what will change before anything is written. */
export function ChatPendingCard({
  card,
  busy,
  onConfirm,
  onCancel,
}: {
  card: ChatCard;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const copy = COPY[card.pending_kind ?? "confirm_cook"];
  const today = localISODate(new Date());
  const item = card.items[0];
  return (
    <Card className="gap-3 rounded-2xl py-4 shadow-sm" role="group" aria-label={card.title}>
      <CardHeader className="px-4">
        <CardTitle className="text-sm">{card.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 px-4 text-sm">
        {item ? (
          <p className="text-muted-foreground">
            {item.name}{" "}
            <span className="tabular-nums">
              {item.quantity} {item.unit}
            </span>
            {item.expires_on ? ` · ${formatExpiry(item.expires_on, today)}` : ""}
          </p>
        ) : null}
        {card.meal ? <p className="text-muted-foreground">{card.meal.title}</p> : null}
        {copy.note ? <p className="text-xs text-muted-foreground">{copy.note}</p> : null}
        <div className="flex gap-2">
          <Button
            type="button"
            variant={copy.destructive ? "destructive" : "default"}
            className="h-11 lg:h-9"
            disabled={busy}
            onClick={onConfirm}
          >
            {copy.confirm}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-11 lg:h-9"
            disabled={busy}
            onClick={onCancel}
          >
            {copy.cancel}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
