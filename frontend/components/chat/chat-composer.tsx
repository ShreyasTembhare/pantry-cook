"use client";

import { ArrowUp } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";

const STARTERS = [
  "2 leeks and 500 g chicken",
  "What's in the pantry?",
  "Something warm for dinner",
];

export function ChatComposer({
  busy,
  suggestions,
  onSend,
}: {
  busy: boolean;
  suggestions: string[];
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const chips = suggestions.length > 0 ? suggestions : STARTERS;

  function submit() {
    const next = text.trim();
    if (!next || busy) return;
    setText("");
    onSend(next);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      className="shrink-0 border-t border-border/70 bg-background/95 px-3 py-3 pb-safe backdrop-blur"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {chips.map((chip) => (
            <button
              key={chip}
              type="button"
              disabled={busy}
              className="shrink-0 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
              onClick={() => onSend(chip)}
            >
              {chip}
            </button>
          ))}
        </div>
        <div className="flex items-end gap-2 rounded-3xl border border-border bg-card p-2 shadow-lg shadow-black/5">
          <label className="sr-only" htmlFor="chat-composer">
            Message Pip
          </label>
          <textarea
            id="chat-composer"
            rows={1}
            value={text}
            disabled={busy}
            placeholder="Add leeks, cook something warm, or change the recipe"
            className="max-h-36 min-h-11 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground"
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
          />
          <Button type="submit" size="icon" disabled={busy || text.trim().length === 0} aria-label="Send">
            <ArrowUp />
          </Button>
        </div>
      </div>
    </form>
  );
}
