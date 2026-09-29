"use client";

import { useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import Link from "next/link";
import { useState } from "react";

import { MealsSkeleton } from "@/components/cook/cook-skeleton";
import { Button } from "@/components/ui/button";
import { ApiError, listMeals, type MealStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

function formatWhen(value: string | null): string {
  if (!value) return "";
  const date = parseISO(value);
  if (Number.isNaN(date.getTime())) return "";
  return format(date, "d MMM yyyy");
}

export function MealsList() {
  const [status, setStatus] = useState<MealStatus>("cooked");
  const mealsQuery = useQuery({
    queryKey: ["meals", status],
    queryFn: () => listMeals(status),
  });

  const meals = mealsQuery.data ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <header className="mb-6">
        <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">Meals</h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
          What you have cooked, newest first.
        </p>
      </header>

      <div className="mb-4 flex gap-2" role="group" aria-label="Meal status">
        {(
          [
            ["cooked", "Cooked"],
            ["proposed", "Proposed"],
            ["undone", "Undone"],
          ] as const
        ).map(([value, label]) => (
          <Button
            key={value}
            type="button"
            variant={status === value ? "secondary" : "ghost"}
            className={cn("h-11 lg:h-9", status === value && "bg-accent text-accent-foreground")}
            aria-pressed={status === value}
            onClick={() => setStatus(value)}
          >
            {label}
          </Button>
        ))}
      </div>

      {mealsQuery.isError ? (
        <div
          role="alert"
          className="mb-4 flex flex-col gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="text-sm leading-relaxed">
            Couldn&apos;t load meals.{" "}
            {mealsQuery.error instanceof ApiError
              ? mealsQuery.error.problem.detail
              : "The list didn't come back."}
          </p>
          <Button
            type="button"
            variant="outline"
            className="h-11 shrink-0 lg:h-9"
            onClick={() => void mealsQuery.refetch()}
          >
            Retry
          </Button>
        </div>
      ) : null}

      {mealsQuery.isPending ? <MealsSkeleton /> : null}

      {mealsQuery.isSuccess && meals.length === 0 ? (
        <div className="max-w-md py-4">
          <p className="text-sm leading-relaxed text-muted-foreground">
            {status === "cooked"
              ? "No meals yet. Cook something."
              : status === "undone"
                ? "No meals have been undone."
                : "Nothing is sitting here as a proposal. An unfinished one stays on Cook until you confirm."}
          </p>
          {status === "cooked" ? (
            <Button asChild className="mt-4 h-11 lg:h-9">
              <Link href="/cook">Cook something</Link>
            </Button>
          ) : null}
        </div>
      ) : null}

      {meals.length > 0 ? (
        <ul className="divide-y divide-border">
          {meals.map((meal) => {
            const when = formatWhen(meal.cooked_at ?? meal.created_at);
            return (
              <li key={meal.id}>
                <Link
                  href={`/meals/${meal.id}`}
                  className="flex flex-col gap-1 py-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:flex-row sm:items-baseline sm:justify-between"
                >
                  <span>
                    <span className="block font-serif text-lg leading-tight tracking-tight">
                      {meal.title}
                    </span>
                    <span className="mt-1 block text-sm text-muted-foreground">
                      {meal.servings} {meal.servings === 1 ? "serving" : "servings"}
                      {when ? ` · ${when}` : ""}
                    </span>
                  </span>
                  <span className="text-sm text-muted-foreground tabular-nums">
                    {meal.use_count} used · {meal.missing_count} to buy
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
