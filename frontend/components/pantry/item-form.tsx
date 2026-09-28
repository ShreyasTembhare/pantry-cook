"use client";

import { useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Unit } from "@/lib/api";
import {
  emptyDraft,
  isDraftEmpty,
  validateDraft,
  type DraftErrors,
  type ItemDraft,
} from "@/lib/quick-add";
import { cn } from "@/lib/utils";

const UNITS: { value: Unit; label: string }[] = [
  { value: "g", label: "g" },
  { value: "kg", label: "kg" },
  { value: "ml", label: "ml" },
  { value: "L", label: "L" },
  { value: "count", label: "count" },
];

type ItemFormProps = {
  idPrefix?: string;
  initial?: ItemDraft;
  submitLabel: string;
  pendingLabel?: string;
  onSubmit: (draft: ItemDraft) => Promise<void> | void;
  onCancel?: () => void;
  cancelLabel?: string;
  clearOnEscape?: boolean;
  autoFocus?: boolean;
  className?: string;
};

export function ItemForm({
  idPrefix,
  initial,
  submitLabel,
  pendingLabel,
  onSubmit,
  onCancel,
  cancelLabel = "Cancel",
  clearOnEscape = false,
  autoFocus = false,
  className,
}: ItemFormProps) {
  const reactId = useId();
  const prefix = idPrefix ?? reactId;
  const nameRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<ItemDraft>(initial ?? emptyDraft());
  const [errors, setErrors] = useState<DraftErrors>({});
  const [pending, setPending] = useState(false);

  function update<K extends keyof ItemDraft>(key: K, value: ItemDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  }

  function reset() {
    setDraft(emptyDraft());
    setErrors({});
    nameRef.current?.focus();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const nextErrors = validateDraft(draft);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    setPending(true);
    try {
      await onSubmit({
        ...draft,
        name: draft.name.trim(),
        quantity: draft.quantity.trim(),
      });
      if (clearOnEscape) reset();
    } catch (error) {
      if (error && typeof error === "object" && "fields" in error) {
        setErrors((error as { fields: DraftErrors }).fields);
      }
    } finally {
      setPending(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    if (clearOnEscape) {
      reset();
      return;
    }
    onCancel?.();
  }

  const dirty = !isDraftEmpty(draft);

  return (
    <form
      onSubmit={handleSubmit}
      onKeyDown={handleKeyDown}
      className={cn("flex flex-col gap-3", className)}
      noValidate
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-[minmax(0,1.5fr)_6.5rem_6.5rem_10rem]">
        <Field label="Name" htmlFor={`${prefix}-name`} error={errors.name} className="col-span-2 lg:col-span-1">
          <Input
            ref={nameRef}
            id={`${prefix}-name`}
            value={draft.name}
            onChange={(event) => update("name", event.target.value)}
            autoFocus={autoFocus}
            autoComplete="off"
            aria-invalid={Boolean(errors.name)}
            placeholder="Leeks"
            className="h-11 lg:h-9"
          />
        </Field>
        <Field label="Quantity" htmlFor={`${prefix}-quantity`} error={errors.quantity}>
          <Input
            id={`${prefix}-quantity`}
            value={draft.quantity}
            onChange={(event) => update("quantity", event.target.value)}
            inputMode="decimal"
            aria-invalid={Boolean(errors.quantity)}
            placeholder="300"
            className="h-11 tabular-nums slashed-zero lg:h-9"
          />
        </Field>
        <Field label="Unit" htmlFor={`${prefix}-unit`}>
          <Select value={draft.unit} onValueChange={(value) => update("unit", value as Unit)}>
            <SelectTrigger id={`${prefix}-unit`} className="h-11 w-full lg:h-9" aria-label="Unit">
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
        </Field>
        <Field
          label="Expiry"
          htmlFor={`${prefix}-expiry`}
          error={errors.expires_on}
          className="col-span-2 lg:col-span-1"
        >
          <Input
            id={`${prefix}-expiry`}
            type="date"
            value={draft.expires_on}
            onChange={(event) => update("expires_on", event.target.value)}
            aria-invalid={Boolean(errors.expires_on)}
            className="h-11 lg:h-9"
          />
        </Field>
      </div>
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={pending} className="h-11 lg:h-9">
          {pending ? (pendingLabel ?? submitLabel) : submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" variant="ghost" className="h-11 lg:h-9" onClick={onCancel} disabled={pending}>
            {cancelLabel}
          </Button>
        ) : null}
        {clearOnEscape && dirty ? (
          <Button type="button" variant="ghost" className="h-11 lg:h-9" onClick={reset}>
            Clear
          </Button>
        ) : null}
      </div>
    </form>
  );
}

function Field({
  label,
  htmlFor,
  error,
  className,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor} className="text-xs font-normal text-muted-foreground">
        {label}
      </Label>
      {children}
      {error ? (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
