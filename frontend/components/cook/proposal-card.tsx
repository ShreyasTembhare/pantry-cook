"use client";

import { ShoppingBag } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { depletionRatio } from "@/lib/quantity";
import { cn } from "@/lib/utils";

export type ProposalLine =
  | { kind: "use"; item_id: string; quantity: string; unit: string }
  | { kind: "missing"; name: string; quantity_note?: string | null };

export type ProposalView = {
  title?: string;
  servings?: number;
  rationale?: string | null;
  lines?: ProposalLine[];
  steps?: string[];
};

export type PantryAmount = {
  name: string;
  quantity: string;
  unit: string;
};

type ProposalCardProps = {
  proposal: ProposalView;
  pantry?: Record<string, PantryAmount>;
  attemptLabel?: string | null;
  stale?: boolean;
  staleMessage?: string;
  busy?: boolean;
  showActions?: boolean;
  onConfirm: () => void;
  onRevise: (note: string) => void;
  onAbandon: () => void;
  onRepropose?: () => void;
};

function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "SELECT")
  );
}

export function ProposalCard({
  proposal,
  pantry = {},
  attemptLabel,
  stale = false,
  staleMessage = "Your pantry changed since this was proposed.",
  busy = false,
  showActions = true,
  onConfirm,
  onRevise,
  onAbandon,
  onRepropose,
}: ProposalCardProps) {
  const noteId = useId();
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const [revising, setRevising] = useState(false);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);
  const [abandoning, setAbandoning] = useState(false);

  const lines = proposal.lines ?? [];
  const steps = proposal.steps ?? [];
  const useLines = lines.filter((line) => line.kind === "use");
  const missingLines = lines.filter((line) => line.kind === "missing");
  const mostlyShopping = useLines.length === 0 && missingLines.length > 0;

  useEffect(() => {
    if (revising) noteRef.current?.focus();
  }, [revising]);

  useEffect(() => {
    if (!showActions) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Escape" && revising) {
        event.preventDefault();
        setRevising(false);
        setNote("");
        setNoteError(null);
        return;
      }
      if (isTypingTarget(event.target) || busy) return;
      if ((event.key === "c" || event.key === "C") && !stale && !revising) {
        event.preventDefault();
        onConfirm();
      }
      if ((event.key === "r" || event.key === "R") && !revising) {
        event.preventDefault();
        setAbandoning(false);
        setRevising(true);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onConfirm, revising, showActions, stale]);

  function submitRevision() {
    const trimmed = note.trim();
    if (!trimmed) {
      setNoteError("Say what should change.");
      noteRef.current?.focus();
      return;
    }
    if (trimmed.length > 300) {
      setNoteError("Keep the note under 300 characters.");
      return;
    }
    onRevise(trimmed);
  }

  return (
    <article
      aria-label={proposal.title || "Proposal"}
      className="rounded-lg border border-border bg-card"
    >
      {stale ? (
        <div
          role="status"
          className="flex flex-col gap-3 border-b border-warning/40 bg-warning/15 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="text-sm leading-relaxed text-warning-foreground">{staleMessage}</p>
          {showActions && onRepropose ? (
            <Button
              type="button"
              variant="outline"
              className="h-11 shrink-0 bg-background lg:h-9"
              onClick={onRepropose}
              disabled={busy}
            >
              Re-propose
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="px-4 py-5 sm:px-5">
        {attemptLabel ? (
          <p className="mb-2 text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
            {attemptLabel}
          </p>
        ) : null}
        {proposal.title ? (
          <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">{proposal.title}</h2>
        ) : (
          <div className="h-7 w-48 rounded-md bg-muted" aria-hidden />
        )}
        {proposal.servings ? (
          <p className="mt-2 text-sm text-muted-foreground tabular-nums">
            {proposal.servings} {proposal.servings === 1 ? "serving" : "servings"}
          </p>
        ) : null}
        {proposal.rationale ? (
          <p className="mt-3 max-w-prose text-sm leading-relaxed text-muted-foreground">
            {proposal.rationale}
          </p>
        ) : null}
        {mostlyShopping ? (
          <p className="mt-3 text-sm leading-relaxed">This is mostly a shopping list.</p>
        ) : null}

        {useLines.length > 0 ? (
          <section className="mt-6" aria-label="Uses">
            <h3 className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
              Uses
            </h3>
            <ul className="mt-2 divide-y divide-border">
              {useLines.map((line) => {
                if (line.kind !== "use") return null;
                const owned = pantry[line.item_id];
                const ratio = owned
                  ? depletionRatio(line.quantity, line.unit, owned.quantity, owned.unit)
                  : null;
                return (
                  <li key={line.item_id} className="py-3">
                    <div className="flex items-baseline justify-between gap-3">
                      <p className="text-sm">{owned?.name ?? "No longer in the pantry"}</p>
                      <p className="shrink-0 text-sm tabular-nums slashed-zero">
                        {line.quantity} {line.unit}
                        {owned ? ` of ${owned.quantity} ${owned.unit}` : ""}
                      </p>
                    </div>
                    {ratio !== null ? (
                      <div className="mt-2 h-0.5 w-full max-w-40 bg-border" aria-hidden>
                        <div
                          data-testid={`depletion-${line.item_id}`}
                          className="h-full bg-primary"
                          style={{ width: `${Math.round(ratio * 100)}%` }}
                        />
                      </div>
                    ) : null}
                    {!owned ? (
                      <p className="mt-1 text-xs text-muted-foreground">That item was removed.</p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null}

        {missingLines.length > 0 ? (
          <section className="mt-6" aria-label="Missing">
            <h3 className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
              Missing
            </h3>
            <ul className="mt-2">
              {missingLines.map((line) => {
                if (line.kind !== "missing") return null;
                return (
                  <li key={line.name} className="flex items-start gap-2 py-2 text-sm">
                    <ShoppingBag
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      strokeWidth={1.75}
                      aria-hidden
                    />
                    <span>
                      {line.name}
                      {line.quantity_note ? (
                        <span className="text-muted-foreground"> · {line.quantity_note}</span>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null}

        {steps.length > 0 ? (
          <section className="mt-6" aria-label="Steps">
            <h3 className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
              Steps
            </h3>
            <ol className="mt-2 max-w-[65ch] list-decimal space-y-2 pl-5 text-sm leading-relaxed">
              {steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </section>
        ) : null}
      </div>

      {showActions ? (
        <footer className="sticky bottom-0 rounded-b-lg border-t border-border bg-card px-4 py-3 sm:px-5">
          {revising ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                submitRevision();
              }}
            >
              <label htmlFor={noteId} className="text-xs text-muted-foreground">
                Revision note
              </label>
              <Textarea
                ref={noteRef}
                id={noteId}
                value={note}
                maxLength={300}
                placeholder="less spicy, fewer steps, use the rice instead"
                aria-invalid={Boolean(noteError)}
                className="mt-1.5 min-h-20"
                onChange={(event) => {
                  setNote(event.target.value);
                  setNoteError(null);
                }}
                onKeyDown={(event) => {
                  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                    event.preventDefault();
                    submitRevision();
                  }
                }}
              />
              {noteError ? (
                <p className="mt-1.5 text-xs text-destructive" role="alert">
                  {noteError}
                </p>
              ) : null}
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <Button type="submit" className="h-11 lg:h-9" disabled={busy}>
                  {busy ? "Revising" : "Send revision"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="h-11 lg:h-9"
                  disabled={busy}
                  onClick={() => {
                    setRevising(false);
                    setNote("");
                    setNoteError(null);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Button
                type="button"
                className="h-11 lg:h-9"
                disabled={busy || stale}
                onClick={onConfirm}
              >
                {busy ? "Cooking" : "Confirm"}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-11 lg:h-9"
                disabled={busy}
                onClick={() => {
                  setAbandoning(false);
                  setRevising(true);
                }}
              >
                Revise
              </Button>
              {abandoning ? (
                <div className="flex flex-col gap-2 sm:ml-auto sm:flex-row sm:items-center">
                  <p className="text-sm text-muted-foreground">Abandon this proposal?</p>
                  <Button
                    type="button"
                    variant="ghost"
                    className={cn("h-11 text-destructive lg:h-9")}
                    disabled={busy}
                    onClick={onAbandon}
                  >
                    Yes, abandon
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-11 lg:h-9"
                    disabled={busy}
                    onClick={() => setAbandoning(false)}
                  >
                    Keep it
                  </Button>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="ghost"
                  className="h-11 sm:ml-auto lg:h-9"
                  disabled={busy}
                  onClick={() => setAbandoning(true)}
                >
                  Abandon
                </Button>
              )}
            </div>
          )}
        </footer>
      ) : null}
    </article>
  );
}
