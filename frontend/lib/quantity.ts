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
