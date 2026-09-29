"use client";

import { useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { MealsSkeleton } from "@/components/cook/cook-skeleton";
import { Button } from "@/components/ui/button";
import { ApiError, getMeal } from "@/lib/api";
import {
  shoppingListEntries,
  shoppingListFilename,
  shoppingListMarkdown,
  shoppingListText,
} from "@/lib/cook";
import { cn } from "@/lib/utils";

function formatWhen(value: string | null): string {
  if (!value) return "";
  const date = parseISO(value);
  if (Number.isNaN(date.getTime())) return "";
  return format(date, "d MMM yyyy");
}

function saveFile(filename: string, contents: string, type: string) {
  const blob = new Blob([contents], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function ShoppingList({ id }: { id: string }) {
  const mealQuery = useQuery({
    queryKey: ["meals", "detail", id],
    queryFn: () => getMeal(id),
  });
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const [copying, setCopying] = useState(false);

  if (mealQuery.isPending) {
    return (
      <div className="mx-auto w-full max-w-xl px-4 py-6 sm:px-6 sm:py-8">
        <MealsSkeleton />
      </div>
    );
  }

  if (mealQuery.isError || !mealQuery.data) {
    const missing =
      mealQuery.error instanceof ApiError && mealQuery.error.problem.code === "meal_not_found";
    return (
      <div className="mx-auto w-full max-w-xl px-4 py-6 sm:px-6 sm:py-8">
        <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">
          {missing ? "Meal not found" : "Couldn't open that list"}
        </h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
          {missing
            ? "That meal isn't in the book, so there is no list to print."
            : mealQuery.error instanceof ApiError
              ? mealQuery.error.problem.detail
              : "The shopping list didn't come back."}
        </p>
        <div className="print-hide mt-4 flex flex-wrap gap-2">
          {missing ? null : (
            <Button
              type="button"
              variant="outline"
              className="h-11 lg:h-9"
              onClick={() => void mealQuery.refetch()}
            >
              Retry
            </Button>
          )}
          <Button asChild variant="ghost" className="h-11 lg:h-9">
            <Link href="/meals">Back to meals</Link>
          </Button>
        </div>
      </div>
    );
  }

  const meal = mealQuery.data;
  const entries = shoppingListEntries(meal.lines);
  const when = formatWhen(meal.cooked_at ?? meal.created_at);
  const servings = `${meal.servings} ${meal.servings === 1 ? "serving" : "servings"}`;

  async function copyList() {
    const text = shoppingListText(meal.lines);
    if (!text) return;
    setCopying(true);
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copied the shopping list.");
    } catch {
      toast.error("Couldn't copy the shopping list.");
    } finally {
      setCopying(false);
    }
  }

  function downloadText() {
    const text = shoppingListText(meal.lines);
    if (!text) return;
    saveFile(
      shoppingListFilename(meal.title, "txt"),
      `${text}\n`,
      "text/plain;charset=utf-8",
    );
  }

  function downloadMarkdown() {
    if (entries.length === 0) return;
    saveFile(
      shoppingListFilename(meal.title, "md"),
      shoppingListMarkdown(meal, meal.lines),
      "text/markdown;charset=utf-8",
    );
  }

  return (
    <div data-shopping-list className="mx-auto w-full max-w-xl px-4 py-6 sm:px-6 sm:py-8">
      <p className="print-hide text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
        <Link href={`/meals/${meal.id}`} className="hover:text-foreground">
          Meal
        </Link>
      </p>
      <h2 className="mt-2 font-serif text-[1.75rem] leading-none tracking-tight">{meal.title}</h2>
      <p className="mt-2 text-sm text-muted-foreground tabular-nums">
        Shopping list
        {` · ${servings}`}
        {when ? ` · ${when}` : ""}
      </p>
      <p className="mt-3 max-w-prose text-sm leading-relaxed text-muted-foreground">
        Only the ingredients this meal does not already have.
      </p>

      {entries.length === 0 ? (
        <p className="mt-6 text-sm leading-relaxed">Nothing to buy for this meal.</p>
      ) : (
        <>
          <div className="print-hide mt-5 flex flex-wrap gap-2">
            <Button type="button" className="h-11 lg:h-9" onClick={() => window.print()}>
              Print
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-11 lg:h-9"
              disabled={copying}
              onClick={() => void copyList()}
            >
              Copy
            </Button>
            <Button type="button" variant="outline" className="h-11 lg:h-9" onClick={downloadText}>
              Download .txt
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-11 lg:h-9"
              onClick={downloadMarkdown}
            >
              Download .md
            </Button>
          </div>
          <ul aria-label="Shopping list" className="mt-6">
            {entries.map((entry, index) => {
              const done = Boolean(checked[index]);
              return (
                <li key={`${entry.name}-${index}`} className="border-b border-border py-2.5">
                  <label className="flex min-h-11 cursor-pointer items-baseline justify-between gap-4 text-sm leading-relaxed">
                    <span className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        className="mt-1 size-4 accent-primary"
                        checked={done}
                        aria-label={entry.note ? `${entry.name}, ${entry.note}` : entry.name}
                        onChange={(event) =>
                          setChecked((current) => ({
                            ...current,
                            [index]: event.target.checked,
                          }))
                        }
                      />
                      <span className={cn(done && "text-muted-foreground line-through")}>
                        {entry.name}
                      </span>
                    </span>
                    {entry.note ? (
                      <span className="shrink-0 text-muted-foreground tabular-nums slashed-zero">
                        {entry.note}
                      </span>
                    ) : null}
                  </label>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
