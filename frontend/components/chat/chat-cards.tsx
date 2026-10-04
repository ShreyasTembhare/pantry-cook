"use client";

import Link from "next/link";

import { ProposalCard, type PantryAmount, type ProposalLine, type ProposalView } from "@/components/cook/proposal-card";
import { Button } from "@/components/ui/button";
import type { ChatCard, Item } from "@/lib/api";

function asProposal(value: Record<string, unknown> | null | undefined): ProposalView | null {
  if (!value || typeof value !== "object") return null;
  const lines: ProposalLine[] = [];
  if (Array.isArray(value.lines)) {
    for (const line of value.lines) {
      if (!line || typeof line !== "object") continue;
      const row = line as Record<string, unknown>;
      if (row.kind === "use" && typeof row.item_id === "string") {
        lines.push({
          kind: "use",
          item_id: row.item_id,
          quantity: String(row.quantity ?? ""),
          unit: String(row.unit ?? ""),
        });
      } else if (row.kind === "missing" && typeof row.name === "string") {
        lines.push({
          kind: "missing",
          name: row.name,
          quantity_note: typeof row.quantity_note === "string" ? row.quantity_note : null,
        });
      }
    }
  }
  return {
    title: typeof value.title === "string" ? value.title : "A meal",
    servings: typeof value.servings === "number" ? value.servings : undefined,
    rationale: typeof value.rationale === "string" ? value.rationale : null,
    steps: Array.isArray(value.steps)
      ? value.steps.filter((step): step is string => typeof step === "string")
      : [],
    lines,
  };
}

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
  onConfirmPending,
  onCancelPending,
  onRevise,
  onAbandon,
  onAskConfirm,
}: {
  cards: ChatCard[];
  pantry: Item[];
  busy: boolean;
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
        if (card.type === "pantry") {
          return (
            <div key={key} className="rounded-2xl border border-border/80 bg-card/80 p-3 shadow-sm">
              <p className="text-sm font-medium">{card.title}</p>
              {card.items.length > 0 ? (
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {card.items.map((item) => (
                    <li key={item.id}>
                      {item.name}{" "}
                      <span className="tabular-nums">
                        {item.quantity} {item.unit}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
              <Link href="/pantry" className="mt-2 inline-block text-xs font-medium text-primary">
                Open pantry
              </Link>
            </div>
          );
        }

        if (card.type === "meals") {
          return (
            <div key={key} className="rounded-2xl border border-border/80 bg-card/80 p-3 shadow-sm">
              <p className="text-sm font-medium">{card.title}</p>
              <ul className="mt-2 space-y-1 text-sm">
                {card.meals.map((meal) => {
                  const id = String(meal.id ?? "");
                  const title = String(meal.title ?? "Meal");
                  return (
                    <li key={id}>
                      <Link href={`/meals/${id}`} className="text-primary">
                        {title}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        }

        if (card.type === "meal" && card.meal) {
          const id = String(card.meal.id ?? "");
          return (
            <div key={key} className="rounded-2xl border border-border/80 bg-card/80 p-3 shadow-sm">
              <p className="text-sm font-medium">{card.title}</p>
              {id ? (
                <Link href={`/meals/${id}`} className="mt-2 inline-block text-xs font-medium text-primary">
                  Open meal
                </Link>
              ) : null}
            </div>
          );
        }

        if (card.type === "error" || card.type === "note") {
          return (
            <p
              key={key}
              className={
                card.type === "error"
                  ? "rounded-2xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
                  : "text-sm text-muted-foreground"
              }
            >
              {card.title}
            </p>
          );
        }

        const proposal = asProposal(card.proposal);
        if ((card.type === "proposal" || card.pending_kind === "confirm_cook") && proposal) {
          const pendingId = card.pending_id;
          return (
            <ProposalCard
              key={key}
              proposal={proposal}
              pantry={amounts}
              busy={busy}
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
          return (
            <div key={key} className="rounded-2xl border border-border/80 bg-card/80 p-3 shadow-sm">
              <p className="text-sm font-medium">{card.title}</p>
              <div className="mt-3 flex gap-2">
                <Button
                  type="button"
                  disabled={busy}
                  onClick={() => onConfirmPending(card.pending_id!, false)}
                >
                  Confirm
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => onCancelPending(card.pending_id!)}
                >
                  Cancel
                </Button>
              </div>
            </div>
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
