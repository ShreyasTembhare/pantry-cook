"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { CookErrorCard } from "@/components/cook/cook-error";
import { CookStartSkeleton } from "@/components/cook/cook-skeleton";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, listItems, startCook } from "@/lib/api";
import {
  EXPIRING_COOK_LABEL,
  cookErrorPresentation,
  retriesSameSentence,
  suggestionChips,
} from "@/lib/cook";
import { localISODate } from "@/lib/pantry";

const PLACEHOLDER = "something quick with the leeks and eggs before they turn";

export function CookStart() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [sentence, setSentence] = useState(searchParams.get("sentence") ?? "");
  const [failure, setFailure] = useState<ApiError | null>(null);
  const today = localISODate(new Date());

  const itemsQuery = useQuery({
    queryKey: ["items"],
    queryFn: listItems,
  });

  const start = useMutation({
    mutationFn: (next: string) => startCook(next, { defer: true }),
    onSuccess: (session) => {
      queryClient.setQueryData(["cook", session.id], session);
      void queryClient.invalidateQueries({ queryKey: ["cook-sessions"] });
      router.push(`/cook/${session.id}`);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setFailure(error);
        if (error.problem.code === "empty_pantry") {
          void queryClient.invalidateQueries({ queryKey: ["items"] });
        }
        return;
      }
      toast.error(error instanceof Error ? error.message : "Couldn't start a cook.");
    },
  });

  const items = itemsQuery.data ?? [];
  const chips = suggestionChips(items, today);
  const empty = itemsQuery.isSuccess && items.length === 0;
  const trimmed = sentence.trim();
  const blank = trimmed.length === 0;
  const tooShort = trimmed.length > 0 && trimmed.length < 3;
  const canPropose = (blank || !tooShort) && trimmed.length <= 500;

  function submit(next = sentence) {
    const value = next.trim();
    const blank = value.length === 0;
    if ((!blank && value.length < 3) || value.length > 500 || start.isPending || empty) return;
    setSentence(value);
    setFailure(null);
    start.mutate(value);
  }

  function recover() {
    if (!failure) return;
    const presentation = cookErrorPresentation(failure.problem.code, failure.problem.detail);
    if (presentation.action === "Add items") {
      router.push("/");
      return;
    }
    if (retriesSameSentence(presentation.action)) {
      submit(sentence);
      return;
    }
    setFailure(null);
    textareaRef.current?.focus();
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <header className="mb-6">
        <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">Cook</h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
          Say what you want, or leave it blank to cook what&apos;s expiring.
        </p>
      </header>

      {itemsQuery.isError ? (
        <div
          role="alert"
          className="mb-4 flex flex-col gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="text-sm leading-relaxed">
            Couldn&apos;t load the pantry.{" "}
            {itemsQuery.error instanceof ApiError
              ? itemsQuery.error.problem.detail
              : "The list didn't come back."}
          </p>
          <Button
            type="button"
            variant="outline"
            className="h-11 shrink-0 lg:h-9"
            onClick={() => void itemsQuery.refetch()}
          >
            Retry
          </Button>
        </div>
      ) : null}

      {itemsQuery.isPending ? <CookStartSkeleton /> : null}

      {empty ? (
        <div className="max-w-md">
          <p className="text-sm leading-relaxed text-muted-foreground">
            The pantry is empty, so there is nothing to cook from. Add what is in the fridge and
            cupboard, then come back with a sentence.
          </p>
          <Button asChild className="mt-4 h-11 lg:h-9">
            <Link href="/">Add items</Link>
          </Button>
        </div>
      ) : null}

      {itemsQuery.isSuccess && !empty ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          {failure ? (
            <div className="mb-4">
              <CookErrorCard
                code={failure.problem.code}
                detail={failure.problem.detail}
                pending={start.isPending}
                onRecover={recover}
              />
            </div>
          ) : null}
          <label htmlFor="cook-sentence" className="sr-only">
            What do you want to cook?
          </label>
          <Textarea
            ref={textareaRef}
            id="cook-sentence"
            value={sentence}
            maxLength={500}
            placeholder={PLACEHOLDER}
            aria-invalid={tooShort}
            disabled={start.isPending}
            onChange={(event) => setSentence(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                submit();
              }
            }}
          />
          {tooShort ? (
            <p className="mt-2 text-xs text-destructive" role="alert">
              A sentence needs at least 3 characters, or leave it blank to cook what&apos;s expiring.
            </p>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              Leave it blank to cook what&apos;s expiring. Propose with ⌘/Ctrl + Enter.
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              className="h-11 lg:h-9"
              disabled={start.isPending}
              onClick={() => submit("")}
            >
              {EXPIRING_COOK_LABEL}
            </Button>
            {chips.map((chip) => (
              <Button
                key={chip.sentence}
                type="button"
                variant="outline"
                className="h-11 lg:h-9"
                disabled={start.isPending}
                onClick={() => {
                  setSentence(chip.sentence);
                  setFailure(null);
                  textareaRef.current?.focus();
                }}
              >
                {chip.label}
              </Button>
            ))}
          </div>
          <Button
            type="submit"
            className="mt-4 h-11 lg:h-9"
            disabled={start.isPending || !canPropose}
          >
            {start.isPending ? "Proposing" : "Propose"}
          </Button>
        </form>
      ) : null}
    </div>
  );
}
