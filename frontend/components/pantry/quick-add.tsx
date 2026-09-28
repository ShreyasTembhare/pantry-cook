"use client";

import { useImperativeHandle, useState } from "react";

import { ItemForm } from "@/components/pantry/item-form";
import { emptyDraft, type ItemDraft } from "@/lib/quick-add";

export type QuickAddHandle = {
  focusName: () => void;
  prefill: (draft: ItemDraft) => void;
};

type QuickAddProps = {
  ref?: React.Ref<QuickAddHandle>;
  onSubmit: (draft: ItemDraft) => Promise<void>;
};

export function QuickAdd({ ref, onSubmit }: QuickAddProps) {
  const [seed, setSeed] = useState(0);
  const [initial, setInitial] = useState<ItemDraft>(emptyDraft());

  useImperativeHandle(ref, () => ({
    focusName: () => {
      document.getElementById("quick-add-name")?.focus();
    },
    prefill: (draft: ItemDraft) => {
      setInitial(draft);
      setSeed((value) => value + 1);
      requestAnimationFrame(() => {
        document.getElementById("quick-add-name")?.focus();
      });
    },
  }));

  return (
    <section aria-label="Add an item" className="border-b border-border pb-5">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-lg leading-none tracking-tight">Add</h3>
        <p className="hidden text-xs text-muted-foreground sm:block">
          Enter adds · Esc clears · / focuses the name
        </p>
      </div>
      <ItemForm
        key={seed}
        idPrefix="quick-add"
        initial={initial}
        submitLabel="Add"
        pendingLabel="Adding"
        clearOnEscape
        onSubmit={async (draft) => {
          await onSubmit(draft);
          requestAnimationFrame(() => {
            document.getElementById("quick-add-name")?.focus();
          });
        }}
      />
    </section>
  );
}
