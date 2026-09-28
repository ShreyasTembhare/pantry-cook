import type { Unit } from "@/lib/api";

export type ItemDraft = {
  name: string;
  quantity: string;
  unit: Unit;
  expires_on: string;
};

export type DraftErrors = Partial<Record<keyof ItemDraft, string>>;

export const emptyDraft = (): ItemDraft => ({
  name: "",
  quantity: "",
  unit: "g",
  expires_on: "",
});

export const SAMPLE_DRAFTS: { label: string; draft: ItemDraft }[] = [
  { label: "500 g rice", draft: { name: "Rice", quantity: "500", unit: "g", expires_on: "" } },
  { label: "6 eggs", draft: { name: "Eggs", quantity: "6", unit: "count", expires_on: "" } },
  { label: "1 L milk", draft: { name: "Milk", quantity: "1", unit: "L", expires_on: "" } },
];

export function draftFromItem(item: {
  name: string;
  quantity: string;
  unit: Unit;
  expires_on: string | null;
}): ItemDraft {
  return {
    name: item.name,
    quantity: item.quantity,
    unit: item.unit,
    expires_on: item.expires_on ?? "",
  };
}

export function validateDraft(draft: ItemDraft): DraftErrors {
  const errors: DraftErrors = {};
  const name = draft.name.trim();

  if (!name) errors.name = "Name the item.";
  else if (name.length > 200) errors.name = "Keep the name under 200 characters.";

  const quantity = draft.quantity.trim();
  if (!quantity) {
    errors.quantity = "Enter a quantity.";
  } else {
    const numeric = Number(quantity);
    if (!Number.isFinite(numeric)) {
      errors.quantity = "Use a number, like 500 or 1.5.";
    } else if (numeric < 0) {
      errors.quantity = "Quantity cannot be negative.";
    } else if (numeric > 1_000_000) {
      errors.quantity = "That amount is too large.";
    } else if (draft.unit === "count" && !Number.isInteger(numeric)) {
      errors.quantity = "Counts must be whole numbers.";
    } else if (draft.unit !== "count" && numeric > 0 && numeric < 0.01) {
      errors.quantity = "Smallest amount is 0.01.";
    }
  }

  return errors;
}

export function isDraftEmpty(draft: ItemDraft): boolean {
  return draft.name.trim() === "" && draft.quantity.trim() === "" && draft.expires_on === "";
}
