const TO_BASE: Record<string, number> = {
  g: 1,
  kg: 1000,
  ml: 1,
  L: 1000,
  count: 1,
};

const DIMENSION: Record<string, string> = {
  g: "mass",
  kg: "mass",
  ml: "volume",
  L: "volume",
  count: "count",
};

export function dimensionOf(unit: string): "mass" | "volume" | "count" | null {
  const value = DIMENSION[unit];
  if (value === "mass" || value === "volume" || value === "count") return value;
  return null;
}

export type NotedQuantity = {
  quantity: string;
  unit: "g" | "kg" | "ml" | "L" | "count";
};

function noteQuantityPattern(): RegExp {
  return /(\d+(?:[.,]\d+)?)\s*(kg|ml|count|g|l)\b/gi;
}

export function parseQuantityNote(note: string | null | undefined): NotedQuantity | null {
  if (!note) return null;
  const matches = [...note.matchAll(noteQuantityPattern())];
  if (matches.length !== 1) return null;
  const rawAmount = matches[0][1]?.replace(",", ".");
  const rawUnit = matches[0][2]?.toLowerCase();
  if (!rawAmount || !rawUnit) return null;
  const numeric = Number(rawAmount);
  if (!Number.isFinite(numeric) || numeric <= 0) return null;
  const unit: NotedQuantity["unit"] = rawUnit === "l" ? "L" : (rawUnit as NotedQuantity["unit"]);
  if (unit === "count" && !Number.isInteger(numeric)) return null;
  if (unit !== "count" && numeric < 0.01) return null;
  return { quantity: trimAmount(numeric), unit };
}

export function knownPurchase(line: {
  quantity?: string | null;
  unit?: NotedQuantity["unit"] | null;
  missing_note?: string | null;
}): NotedQuantity | null {
  if (line.quantity && line.unit) {
    const numeric = Number(line.quantity);
    if (Number.isFinite(numeric) && numeric > 0) {
      return { quantity: trimAmount(numeric), unit: line.unit };
    }
  }
  return parseQuantityNote(line.missing_note);
}

export function trimAmount(value: number): string {
  if (!Number.isFinite(value)) return "";
  const rounded = Math.round((value + Number.EPSILON) * 100) / 100;
  if (rounded === 0) return "0";
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export function parseAmount(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return null;
  return trimAmount(numeric);
}

export function depletionRatio(
  requested: string,
  requestedUnit: string,
  available: string,
  availableUnit: string,
): number | null {
  const requestedFactor = TO_BASE[requestedUnit];
  const availableFactor = TO_BASE[availableUnit];
  if (requestedFactor === undefined || availableFactor === undefined) return null;
  if (DIMENSION[requestedUnit] !== DIMENSION[availableUnit]) return null;
  const requestedBase = Number(requested) * requestedFactor;
  const availableBase = Number(available) * availableFactor;
  if (!Number.isFinite(requestedBase) || !Number.isFinite(availableBase)) return null;
  if (availableBase <= 0) return 1;
  return Math.min(1, Math.max(0, requestedBase / availableBase));
}
