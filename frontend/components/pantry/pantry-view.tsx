"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ItemForm } from "@/components/pantry/item-form";
import { PantryRow } from "@/components/pantry/pantry-row";
import { PantrySkeleton } from "@/components/pantry/pantry-skeleton";
import { QuickAdd, type QuickAddHandle } from "@/components/pantry/quick-add";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ApiError,
  createItem,
  deleteItem,
  fieldErrorsFromProblem,
  listItems,
  updateItem,
  type Item,
} from "@/lib/api";
import { groupItems, localISODate } from "@/lib/pantry";
import { SAMPLE_DRAFTS, draftFromItem, type ItemDraft } from "@/lib/quick-add";

class DraftFieldError extends Error {
  fields: Partial<Record<string, string>>;

  constructor(fields: Partial<Record<string, string>>, message: string) {
    super(message);
    this.fields = fields;
  }
}

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(max-width: 1023px)");
    const apply = () => setIsMobile(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  return isMobile;
}

export function PantryView() {
  const queryClient = useQueryClient();
  const quickAddRef = useRef<QuickAddHandle>(null);
  const mobile = useIsMobile();
  const [today, setToday] = useState(() => localISODate(new Date()));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [sheetItem, setSheetItem] = useState<Item | null>(null);
  const [settlingId, setSettlingId] = useState<string | null>(null);

  const itemsQuery = useQuery({
    queryKey: ["items"],
    queryFn: listItems,
  });

  useEffect(() => {
    const refresh = () => setToday(localISODate(new Date()));
    refresh();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable ||
          target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT")
      ) {
        return;
      }
      event.preventDefault();
      quickAddRef.current?.focusName();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function invalidate() {
    return queryClient.invalidateQueries({ queryKey: ["items"] });
  }

  function throwIfFields(error: unknown): never {
    if (error instanceof ApiError) {
      const fields = fieldErrorsFromProblem(error.problem);
      if (Object.keys(fields).length > 0) {
        throw new DraftFieldError(fields, error.problem.detail);
      }
      toast.error(error.problem.detail);
      if (error.problem.code === "stale_version") void invalidate();
      throw error;
    }
    toast.error(error instanceof Error ? error.message : "Couldn't save that item.");
    throw error;
  }

  const createMutation = useMutation({
    mutationFn: (draft: ItemDraft) =>
      createItem({
        name: draft.name,
        quantity: draft.quantity,
        unit: draft.unit,
        expires_on: draft.expires_on || null,
      }),
    onSuccess: async (item) => {
      await invalidate();
      setSettlingId(item.id);
      window.setTimeout(() => setSettlingId((current) => (current === item.id ? null : current)), 400);
      toast.success(`Added ${item.name}`);
      quickAddRef.current?.focusName();
    },
    onError: (error) => {
      if (error instanceof DraftFieldError) return;
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ item, draft }: { item: Item; draft: ItemDraft }) =>
      updateItem(item.id, {
        name: draft.name,
        quantity: draft.quantity,
        unit: draft.unit,
        expires_on: draft.expires_on || null,
        version: item.version,
      }),
    onSuccess: async (item) => {
      await invalidate();
      setEditingId(null);
      setSheetItem(null);
      toast.success(`Updated ${item.name}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (item: Item) => deleteItem(item.id),
    onSuccess: async (_void, item) => {
      await invalidate();
      if (editingId === item.id) setEditingId(null);
      if (sheetItem?.id === item.id) setSheetItem(null);
      toast.success(`Removed ${item.name}`);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.problem.detail : "Couldn't remove that item.");
    },
  });

  async function handleCreate(draft: ItemDraft) {
    try {
      await createMutation.mutateAsync(draft);
    } catch (error) {
      throwIfFields(error);
    }
  }

  async function handleSave(item: Item, draft: ItemDraft) {
    try {
      await updateMutation.mutateAsync({ item, draft });
    } catch (error) {
      throwIfFields(error);
    }
  }

  function startEdit(item: Item) {
    if (mobile) {
      setEditingId(null);
      setSheetItem(item);
      return;
    }
    setSheetItem(null);
    setEditingId(item.id);
  }

  const items = itemsQuery.data ?? [];
  const groups = groupItems(items, today);
  const showEmpty = itemsQuery.isSuccess && items.length === 0;
  const showSkeleton = itemsQuery.isPending;
  const showError = itemsQuery.isError;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <header className="mb-6">
        <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">Pantry</h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
          {itemsQuery.isSuccess && items.length > 0
            ? `${items.length} ${items.length === 1 ? "item" : "items"}, soonest first.`
            : "What's in the fridge and cupboard, soonest first."}
        </p>
      </header>

      <QuickAdd ref={quickAddRef} onSubmit={handleCreate} />

      <div className="mt-6">
        {showError ? (
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

        {showSkeleton ? <PantrySkeleton /> : null}

        {showEmpty ? (
          <div className="py-8">
            <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
              Your pantry is empty. Add what&apos;s in the fridge and cupboard — the cook uses what
              you actually have.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {SAMPLE_DRAFTS.map((sample) => (
                <Button
                  key={sample.label}
                  type="button"
                  variant="outline"
                  className="h-11 lg:h-9"
                  onClick={() => quickAddRef.current?.prefill(sample.draft)}
                >
                  {sample.label}
                </Button>
              ))}
            </div>
          </div>
        ) : null}

        {groups.map((group) => (
          <section key={group.urgency} aria-label={group.label} className="mb-6">
            <h3
              className={
                group.urgency === "expired"
                  ? "mb-1 text-xs font-medium tracking-[0.14em] text-expired uppercase"
                  : group.urgency === "soon"
                    ? "mb-1 text-xs font-medium tracking-[0.14em] text-warning-foreground uppercase"
                    : "mb-1 text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase"
              }
            >
              {group.label}
            </h3>
            <ul>
              {group.items.map((item) => (
                <PantryRow
                  key={item.id}
                  item={item}
                  today={today}
                  editing={!mobile && editingId === item.id}
                  settle={settlingId === item.id}
                  mobile={mobile}
                  onStartEdit={() => startEdit(item)}
                  onCancelEdit={() => setEditingId(null)}
                  onSave={(draft) => handleSave(item, draft)}
                  onDelete={() => deleteMutation.mutateAsync(item)}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>

      <Sheet open={sheetItem !== null} onOpenChange={(open) => !open && setSheetItem(null)}>
        <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto pb-8">
          {sheetItem ? (
            <>
              <SheetHeader>
                <SheetTitle className="font-serif text-xl">Edit {sheetItem.name}</SheetTitle>
                <SheetDescription>Quantity, unit, and an optional expiry.</SheetDescription>
              </SheetHeader>
              <div className="px-4">
                <ItemForm
                  idPrefix={`sheet-${sheetItem.id}`}
                  initial={draftFromItem(sheetItem)}
                  submitLabel="Save"
                  pendingLabel="Saving"
                  autoFocus
                  onSubmit={(draft) => handleSave(sheetItem, draft)}
                  onCancel={() => setSheetItem(null)}
                />
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
