"use client";

import NumberFlow from "@number-flow/react";
import { MoreHorizontal } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";

import { ItemForm } from "@/components/pantry/item-form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { Item } from "@/lib/api";
import { formatExpiry, urgencyOf, type Urgency } from "@/lib/pantry";
import { draftFromItem, type ItemDraft } from "@/lib/quick-add";
import { cn } from "@/lib/utils";

type PantryRowProps = {
  item: Item;
  today: string;
  editing: boolean;
  settle?: boolean;
  mobile?: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSave: (draft: ItemDraft) => Promise<void>;
  onDelete: () => Promise<void> | void;
};

export function PantryRow({
  item,
  today,
  editing,
  settle = false,
  mobile = false,
  onStartEdit,
  onCancelEdit,
  onSave,
  onDelete,
}: PantryRowProps) {
  const reduceMotion = useReducedMotion();
  const urgency = urgencyOf(item, today);
  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState(false);
  const amount = Number(item.quantity);
  const expiry = item.expires_on ? formatExpiry(item.expires_on, today) : "No date";

  async function confirmDelete() {
    setRemoving(true);
    try {
      await onDelete();
      setConfirming(false);
    } finally {
      setRemoving(false);
    }
  }

  return (
    <motion.li
      layout={reduceMotion ? false : "position"}
      initial={settle && !reduceMotion ? { opacity: 0, y: 6 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        layout: { type: "spring", stiffness: 300, damping: 30 },
        opacity: { duration: 0.2 },
        y: { duration: 0.2 },
      }}
      className="border-b border-border last:border-b-0"
      data-testid="pantry-row"
      data-urgency={urgency}
    >
      {editing ? (
        <div className="py-3">
          <ItemForm
            idPrefix={`edit-${item.id}`}
            initial={draftFromItem(item)}
            submitLabel="Save"
            pendingLabel="Saving"
            autoFocus
            onSubmit={onSave}
            onCancel={onCancelEdit}
          />
        </div>
      ) : (
        <div
          className={cn(
            "group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 py-2.5 sm:grid-cols-[minmax(0,1.4fr)_7rem_minmax(8rem,auto)_2.75rem]",
            urgency === "out" && "text-muted-foreground",
          )}
        >
          <button
            type="button"
            className="min-h-11 min-w-0 rounded-md text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            onClick={onStartEdit}
          >
            <span className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-medium text-foreground">{item.name}</span>
              <UrgencyChip urgency={urgency} expiredToo={urgency === "out" && Boolean(item.expires_on && item.expires_on < today)} />
            </span>
          </button>
          <p
            data-testid="quantity"
            className="text-sm tabular-nums slashed-zero sm:text-right"
          >
            <NumberFlow
              value={Number.isFinite(amount) ? amount : 0}
              format={
                item.unit === "count"
                  ? { maximumFractionDigits: 0 }
                  : { maximumFractionDigits: 2 }
              }
            />
            <span className="ml-1 text-muted-foreground">{item.unit}</span>
          </p>
          <p className="col-start-1 text-xs text-muted-foreground sm:col-start-auto sm:text-sm">
            {expiry}
          </p>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-11 justify-self-end lg:size-8"
                aria-label={`Actions for ${item.name}`}
                onClick={(event) => event.stopPropagation()}
              >
                <MoreHorizontal strokeWidth={1.75} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={() => {
                  onStartEdit();
                }}
              >
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onSelect={() => setConfirming(true)}>
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {mobile ? (
        <Sheet open={confirming} onOpenChange={setConfirming}>
          <SheetContent side="bottom" className="pb-8">
            <SheetHeader>
              <SheetTitle className="font-serif text-xl">Remove {item.name}?</SheetTitle>
              <SheetDescription>
                It leaves the pantry. Meals you have already cooked keep the name.
              </SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-2 px-4">
              <Button
                type="button"
                variant="destructive"
                className="h-11"
                disabled={removing}
                onClick={() => void confirmDelete()}
              >
                {removing ? "Removing" : "Remove"}
              </Button>
              <Button type="button" variant="ghost" className="h-11" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </div>
          </SheetContent>
        </Sheet>
      ) : (
        <Dialog open={confirming} onOpenChange={setConfirming}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="font-serif text-xl">Remove {item.name}?</DialogTitle>
              <DialogDescription>
                It leaves the pantry. Meals you have already cooked keep the name.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                disabled={removing}
                onClick={() => void confirmDelete()}
              >
                {removing ? "Removing" : "Remove"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </motion.li>
  );
}

function UrgencyChip({ urgency, expiredToo }: { urgency: Urgency; expiredToo: boolean }) {
  if (urgency === "fresh") return null;
  return (
    <span className="inline-flex items-center gap-1">
      {urgency === "expired" ? <Chip tone="expired">Expired</Chip> : null}
      {urgency === "soon" ? <Chip tone="soon">Use soon</Chip> : null}
      {urgency === "out" ? <Chip tone="out">Out</Chip> : null}
      {expiredToo ? <Chip tone="expired">Expired</Chip> : null}
    </span>
  );
}

function Chip({ tone, children }: { tone: "expired" | "soon" | "out"; children: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium tracking-wide",
        tone === "expired" && "bg-expired/10 text-expired",
        tone === "soon" && "bg-warning/25 text-warning-foreground",
        tone === "out" && "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}
