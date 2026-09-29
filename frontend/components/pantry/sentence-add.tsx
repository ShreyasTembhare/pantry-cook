"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ApiError,
  previewPantrySentence,
  savePantrySentence,
  type Item,
  type SentencePreview,
} from "@/lib/api";
import { trimAmount } from "@/lib/quantity";

type SentenceAddProps = {
  onAdded: (items: Item[]) => void;
};

export function SentenceAdd({ onAdded }: SentenceAddProps) {
  const [sentence, setSentence] = useState("");
  const [preview, setPreview] = useState<SentencePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<"preview" | "save" | null>(null);

  function resetPreview() {
    setPreview(null);
    setError(null);
  }

  async function handlePreview() {
    const text = sentence.trim();
    if (!text) {
      setPreview(null);
      setError('Say what to add, like "2 leeks and 500 g chicken".');
      return;
    }
    setPending("preview");
    setError(null);
    try {
      setPreview(await previewPantrySentence(text));
    } catch (caught) {
      setPreview(null);
      setError(messageFrom(caught));
    } finally {
      setPending(null);
    }
  }

  async function handleSave() {
    if (!preview) return;
    setPending("save");
    setError(null);
    try {
      const items = await savePantrySentence(
        preview.items.map((item) => ({
          name: item.name,
          quantity: item.quantity,
          unit: item.unit,
        })),
      );
      setSentence("");
      setPreview(null);
      onAdded(items);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setPending(null);
    }
  }

  return (
    <section aria-label="Add from a sentence" className="border-b border-border pb-5">
      <div className="mb-3">
        <h3 className="font-serif text-lg leading-none tracking-tight">From a sentence</h3>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
          Name quantities in one line. Nothing is saved until you add the preview.
        </p>
      </div>
      <form
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          void handlePreview();
        }}
      >
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <Label htmlFor="sentence-add" className="text-xs font-normal text-muted-foreground">
            Sentence
          </Label>
          <Input
            id="sentence-add"
            value={sentence}
            onChange={(event) => {
              setSentence(event.target.value);
              resetPreview();
            }}
            placeholder="2 leeks and 500 g chicken"
            autoComplete="off"
            aria-invalid={Boolean(error)}
            className="h-11 lg:h-9"
          />
        </div>
        <Button type="submit" disabled={pending !== null} className="h-11 lg:h-9">
          {pending === "preview" ? "Reading" : "Preview"}
        </Button>
      </form>
      {error ? (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {preview ? (
        <div className="mt-3">
          <ul aria-label="Preview" className="divide-y divide-border border-y border-border">
            {preview.items.map((item) => (
              <li
                key={`${item.name}-${item.unit}`}
                className="flex items-baseline justify-between gap-3 py-2 text-sm"
              >
                <span className="font-medium">{item.name}</span>
                <span className="tabular-nums text-muted-foreground slashed-zero">
                  {trimAmount(Number(item.quantity))} {item.unit}
                  {" · "}
                  {item.action === "add" ? "adds to the pantry" : "new"}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex items-center gap-2">
            <Button
              type="button"
              disabled={pending !== null}
              className="h-11 lg:h-9"
              onClick={() => void handleSave()}
            >
              {pending === "save" ? "Adding" : "Add these"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="h-11 lg:h-9"
              disabled={pending !== null}
              onClick={() => {
                setSentence("");
                resetPreview();
              }}
            >
              Clear
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function messageFrom(caught: unknown): string {
  if (caught instanceof ApiError) return caught.problem.detail;
  return "Couldn't read that sentence.";
}
