"use client";

import { Button } from "@/components/ui/button";

type DuplicatePromptProps = {
  name: string;
  quantity: string;
  unit: string;
  sameDimension: boolean;
  pending?: boolean;
  onMerge: () => void;
  onRename: () => void;
};

export function DuplicatePrompt({
  name,
  quantity,
  unit,
  sameDimension,
  pending = false,
  onMerge,
  onRename,
}: DuplicatePromptProps) {
  return (
    <div
      role="status"
      className="mt-4 rounded-md border border-warning/40 bg-warning/15 px-3 py-3"
    >
      <p className="text-sm leading-relaxed text-warning-foreground">
        {sameDimension
          ? `${name} is already in the pantry.`
          : `${name} is already in the pantry, in a different measure. Rename this one.`}
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        {sameDimension ? (
          <Button type="button" className="h-11 lg:h-9" disabled={pending} onClick={onMerge}>
            {pending ? "Adding" : `Add ${quantity} ${unit} to it`}
          </Button>
        ) : null}
        <Button
          type="button"
          variant="outline"
          className="h-11 bg-background lg:h-9"
          disabled={pending}
          onClick={onRename}
        >
          Rename
        </Button>
      </div>
    </div>
  );
}
