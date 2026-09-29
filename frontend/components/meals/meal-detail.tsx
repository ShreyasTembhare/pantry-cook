"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { MealsSkeleton } from "@/components/cook/cook-skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, buyMissingLine, getMeal, undoMeal, type MealLine, type Unit } from "@/lib/api";
import { displayCookSentence, shoppingListText } from "@/lib/cook";
import { knownPurchase } from "@/lib/quantity";
import { cn } from "@/lib/utils";

const UNITS: { value: Unit; label: string }[] = [
  { value: "g", label: "g" },
  { value: "kg", label: "kg" },
  { value: "ml", label: "ml" },
  { value: "L", label: "L" },
  { value: "count", label: "count" },
];

function purchaseError(quantity: string, unit: Unit): string | null {
  const trimmed = quantity.trim();
  if (!trimmed) return "Enter a quantity.";
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric)) return "Use a number, like 200 or 1.5.";
  if (numeric <= 0) return "Quantity has to be more than zero.";
  if (numeric > 1_000_000) return "That amount is too large.";
  if (unit === "count" && !Number.isInteger(numeric)) return "Counts must be whole numbers.";
  if (unit !== "count" && numeric < 0.01) return "Smallest amount is 0.01.";
  return null;
}

function formatWhen(value: string | null): string {
  if (!value) return "";
  const date = parseISO(value);
  if (Number.isNaN(date.getTime())) return "";
  return format(date, "d MMM yyyy");
}

function lineAmount(line: MealLine): string {
  if (!line.quantity || !line.unit) return "";
  return `${line.quantity} ${line.unit}`;
}

export function MealDetail({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const mealQuery = useQuery({
    queryKey: ["meals", "detail", id],
    queryFn: () => getMeal(id),
  });
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [copying, setCopying] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [ask, setAsk] = useState<{
    lineId: string;
    quantity: string;
    unit: Unit;
    error: string;
  } | null>(null);
  const buy = useMutation({
    mutationFn: (input: { lineId: string; purchase?: { quantity: string; unit: Unit } }) =>
      buyMissingLine(id, input.lineId, input.purchase),
    onSuccess: (result) => {
      queryClient.setQueryData(["meals", "detail", id], result.meal);
      void queryClient.invalidateQueries({ queryKey: ["meals", "cooked"] });
      void queryClient.invalidateQueries({ queryKey: ["meals", "proposed"] });
      void queryClient.invalidateQueries({ queryKey: ["meals", "undone"] });
      void queryClient.invalidateQueries({ queryKey: ["items"] });
      setAsk(null);
      const amount = `${result.quantity} ${result.unit}`;
      toast.success(
        result.created
          ? `Bought ${amount} of ${result.item_name}.`
          : `Added ${amount} to ${result.item_name}.`,
      );
    },
    onError: (error, variables) => {
      if (error instanceof ApiError && error.problem.code === "quantity_required") {
        setAsk({ lineId: variables.lineId, quantity: "", unit: "g", error: "" });
        return;
      }
      toast.error(
        error instanceof ApiError ? error.problem.detail : "Couldn't add that to the pantry.",
      );
    },
  });
  const undo = useMutation({
    mutationFn: () => undoMeal(id),
    onSuccess: (meal) => {
      queryClient.setQueryData(["meals", "detail", id], meal);
      void queryClient.invalidateQueries({ queryKey: ["meals", "cooked"] });
      void queryClient.invalidateQueries({ queryKey: ["meals", "proposed"] });
      void queryClient.invalidateQueries({ queryKey: ["meals", "undone"] });
      void queryClient.invalidateQueries({ queryKey: ["items"] });
      setConfirmOpen(false);
      toast.success("Undone. Pantry quantities restored.");
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiError ? error.problem.detail : "Couldn't undo that meal.",
      );
    },
  });

  if (mealQuery.isPending) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        <MealsSkeleton />
      </div>
    );
  }

  if (mealQuery.isError || !mealQuery.data) {
    const missing =
      mealQuery.error instanceof ApiError && mealQuery.error.problem.code === "meal_not_found";
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">
          {missing ? "Meal not found" : "Couldn't open that meal"}
        </h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
          {missing
            ? "That meal isn't in the book. It may have been cooked against a different pantry."
            : mealQuery.error instanceof ApiError
              ? mealQuery.error.problem.detail
              : "The meal didn't come back."}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
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
  const used = meal.lines.filter((line) => line.kind === "use");
  const missing = meal.lines.filter((line) => line.kind === "missing");
  const when = formatWhen(meal.cooked_at ?? meal.created_at);

  async function copyList() {
    const text = shoppingListText(missing);
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

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <p className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
        <Link href="/meals" className="hover:text-foreground">
          Meals
        </Link>
      </p>
      <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">{meal.title}</h2>
          <p className="mt-2 text-sm text-muted-foreground tabular-nums">
            {meal.servings} {meal.servings === 1 ? "serving" : "servings"}
            {when ? ` · ${when}` : ""}
          </p>
        </div>
        {meal.status === "cooked" ? (
          <Button
            type="button"
            variant="outline"
            className="h-11 lg:h-9"
            onClick={() => setConfirmOpen(true)}
          >
            Undo
          </Button>
        ) : null}
      </div>
      {meal.status === "undone" ? (
        <p
          role="status"
          className="mt-4 rounded-md border border-border bg-muted/70 px-3 py-3 text-sm leading-relaxed"
        >
          <span className="font-medium">Undone.</span> The quantities this meal used are back in
          the pantry.
        </p>
      ) : null}
      <blockquote className="mt-4 max-w-prose border-l-2 border-border pl-3 text-sm leading-relaxed text-muted-foreground">
        {displayCookSentence(meal.sentence)}
      </blockquote>
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Undo this meal?</DialogTitle>
            <DialogDescription>
              The pantry gets back what this meal used. Undoing again will not add those amounts a
              second time.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              className="h-11 lg:h-9"
              onClick={() => setConfirmOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              className="h-11 lg:h-9"
              disabled={undo.isPending}
              onClick={() => undo.mutate()}
            >
              {undo.isPending ? "Undoing" : "Undo meal"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="mt-8 grid gap-8 sm:grid-cols-2">
        <section aria-label="Used from pantry">
          <h3 className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
            Used from pantry
          </h3>
          {used.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">Nothing was taken from the pantry.</p>
          ) : (
            <ul className="mt-2 divide-y divide-border">
              {used.map((line) => (
                <li key={line.id} className="flex items-baseline justify-between gap-3 py-2.5 text-sm">
                  <span>
                    {line.item_name}
                    {line.item_id ? null : (
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        No longer in the pantry
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 tabular-nums slashed-zero">{lineAmount(line)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Shopping list">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
              Shopping list
            </h3>
            {missing.length > 0 ? (
              <Button
                type="button"
                variant="outline"
                className="h-11 lg:h-8"
                disabled={copying}
                onClick={() => void copyList()}
              >
                Copy
              </Button>
            ) : null}
          </div>
          {missing.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">Nothing to buy for this meal.</p>
          ) : (
            <ul className="mt-2">
              {missing.map((line) => {
                const name = line.missing_name || line.item_name;
                const done = Boolean(checked[line.id]);
                const pending = buy.isPending && buy.variables?.lineId === line.id;
                const asking = ask?.lineId === line.id ? ask : null;
                return (
                  <li key={line.id} className="py-1.5">
                    <div className="flex items-start justify-between gap-3">
                      <label className="flex min-h-11 cursor-pointer items-start gap-3 text-sm leading-relaxed">
                        <input
                          type="checkbox"
                          className="mt-1 size-4 accent-primary"
                          checked={done}
                          onChange={(event) =>
                            setChecked((current) => ({
                              ...current,
                              [line.id]: event.target.checked,
                            }))
                          }
                        />
                        <span className={cn(done && "text-muted-foreground line-through")}>
                          {name}
                          {line.missing_note ? (
                            <span className="text-muted-foreground"> · {line.missing_note}</span>
                          ) : null}
                        </span>
                      </label>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-11 shrink-0 lg:h-8"
                        aria-label={`I bought this: ${name}`}
                        disabled={buy.isPending}
                        onClick={() => {
                          const known = knownPurchase(line);
                          if (!known) {
                            setAsk({ lineId: line.id, quantity: "", unit: "g", error: "" });
                            return;
                          }
                          buy.mutate({ lineId: line.id, purchase: known });
                        }}
                      >
                        {pending ? "Adding" : "I bought this"}
                      </Button>
                    </div>
                    {asking ? (
                      <form
                        className="mt-2 flex flex-wrap items-end gap-2 pl-7"
                        onSubmit={(event) => {
                          event.preventDefault();
                          const message = purchaseError(asking.quantity, asking.unit);
                          if (message) {
                            setAsk({ ...asking, error: message });
                            return;
                          }
                          buy.mutate({
                            lineId: line.id,
                            purchase: { quantity: asking.quantity.trim(), unit: asking.unit },
                          });
                        }}
                      >
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`bought-${line.id}-quantity`} className="text-xs font-normal text-muted-foreground">
                            Quantity
                          </Label>
                          <Input
                            id={`bought-${line.id}-quantity`}
                            value={asking.quantity}
                            onChange={(event) =>
                              setAsk({ ...asking, quantity: event.target.value, error: "" })
                            }
                            inputMode="decimal"
                            autoFocus
                            aria-invalid={Boolean(asking.error)}
                            placeholder="200"
                            className="h-11 w-24 tabular-nums slashed-zero lg:h-9"
                          />
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`bought-${line.id}-unit`} className="text-xs font-normal text-muted-foreground">
                            Unit
                          </Label>
                          <Select
                            value={asking.unit}
                            onValueChange={(value) =>
                              setAsk({ ...asking, unit: value as Unit, error: "" })
                            }
                          >
                            <SelectTrigger
                              id={`bought-${line.id}-unit`}
                              className="h-11 w-24 lg:h-9"
                              aria-label={`Unit for ${name}`}
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {UNITS.map((unit) => (
                                <SelectItem key={unit.value} value={unit.value}>
                                  {unit.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <Button type="submit" className="h-11 lg:h-9" disabled={buy.isPending}>
                          Add to pantry
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          className="h-11 lg:h-9"
                          onClick={() => setAsk(null)}
                        >
                          Cancel
                        </Button>
                        {asking.error ? (
                          <p className="w-full text-xs text-destructive" role="alert">
                            {asking.error}
                          </p>
                        ) : null}
                      </form>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      {meal.steps.length > 0 ? (
        <section className="mt-8" aria-label="Steps">
          <h3 className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
            Steps
          </h3>
          <ol className="mt-3 max-w-[65ch] list-decimal space-y-3 pl-5 text-sm leading-relaxed">
            {meal.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
