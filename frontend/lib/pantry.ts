import { format } from "date-fns";

import type { Item } from "@/lib/api";

export type Urgency = "expired" | "soon" | "fresh" | "out";

export const URGENCY_ORDER: Urgency[] = ["expired", "soon", "fresh", "out"];

export const URGENCY_LABEL: Record<Urgency, string> = {
  expired: "Expired",
  soon: "Use soon",
  fresh: "Everything else",
  out: "Out",
};

const SOON_DAYS = 3;

export function localISODate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseISODate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, (month ?? 1) - 1, day ?? 1);
}

export function addDaysISO(iso: string, days: number): string {
  const date = parseISODate(iso);
  date.setDate(date.getDate() + days);
  return localISODate(date);
}

export function isOut(quantity: string): boolean {
  const numeric = Number(quantity);
  return Number.isFinite(numeric) && numeric === 0;
}

export function urgencyOf(item: Pick<Item, "quantity" | "expires_on">, today: string): Urgency {
  if (isOut(item.quantity)) return "out";
  if (item.expires_on && item.expires_on < today) return "expired";
  if (item.expires_on && item.expires_on <= addDaysISO(today, SOON_DAYS)) return "soon";
  return "fresh";
}

export function formatExpiry(expiresOn: string, today: string): string {
  const weekday = format(parseISODate(expiresOn), "EEE");
  const days = differenceInDays(expiresOn, today);
  if (days === 0) return `${weekday}, today`;
  if (days === 1) return `${weekday}, tomorrow`;
  if (days > 1) return `${weekday}, in ${days} days`;
  if (days === -1) return `${weekday}, yesterday`;
  return `${weekday}, ${Math.abs(days)} days ago`;
}

function differenceInDays(later: string, earlier: string): number {
  const msPerDay = 24 * 60 * 60 * 1000;
  return Math.round((parseISODate(later).getTime() - parseISODate(earlier).getTime()) / msPerDay);
}

export type PantryGroup = {
  urgency: Urgency;
  label: string;
  items: Item[];
};

export function groupItems(items: Item[], today: string): PantryGroup[] {
  const buckets: Record<Urgency, Item[]> = {
    expired: [],
    soon: [],
    fresh: [],
    out: [],
  };

  const sorted = [...items].sort((a, b) => {
    const expiry = (a.expires_on ?? "9999-99-99").localeCompare(b.expires_on ?? "9999-99-99");
    if (expiry !== 0) return expiry;
    return a.name.localeCompare(b.name);
  });

  for (const item of sorted) {
    buckets[urgencyOf(item, today)].push(item);
  }

  return URGENCY_ORDER.filter((urgency) => buckets[urgency].length > 0).map((urgency) => ({
    urgency,
    label: URGENCY_LABEL[urgency],
    items: buckets[urgency],
  }));
}
