import { addDaysISO } from "@/lib/pantry";

export type ChipItem = {
  id: string;
  name: string;
  quantity: string;
  expires_on: string | null;
};

export type Suggestion = {
  label: string;
  sentence: string;
};

const SOON_DAYS = 3;

export function suggestionChips(items: ChipItem[], today: string): Suggestion[] {
  const available = items.filter((item) => {
    const quantity = Number(item.quantity);
    return Number.isFinite(quantity) && quantity > 0;
  });
  const dated = available
    .filter((item) => item.expires_on)
    .sort((a, b) => (a.expires_on ?? "").localeCompare(b.expires_on ?? ""));
  const horizon = addDaysISO(today, SOON_DAYS);
  const soon = dated.filter(
    (item) => item.expires_on !== null && item.expires_on >= today && item.expires_on <= horizon,
  );
  const lead = soon[0] ?? dated[0] ?? available[0];
  if (!lead) return [];

  const second =
    soon.find((item) => item.id !== lead.id) ??
    dated.find((item) => item.id !== lead.id) ??
    available.find((item) => item.id !== lead.id);

  const leadName = lead.name.toLocaleLowerCase();
  const chips: Suggestion[] = [];
  if (lead.expires_on) {
    chips.push({
      label: `Use the ${leadName}`,
      sentence: `use the ${leadName} before it goes off`,
    });
  }
  if (second) {
    chips.push({
      label: `${lead.name} and ${second.name}`,
      sentence: `something quick with the ${leadName} and ${second.name.toLocaleLowerCase()} before they turn`,
    });
  }
  chips.push({
    label: "Something warm",
    sentence: `something warm with the ${leadName}`,
  });

  const seen = new Set<string>();
  return chips
    .filter((chip) => {
      if (seen.has(chip.sentence)) return false;
      seen.add(chip.sentence);
      return true;
    })
    .slice(0, 3);
}

const KNOWN_ERRORS: Record<string, { message: string; action: string }> = {
  llm_timeout: { message: "The chef took too long.", action: "Try again" },
  llm_rate_limited: {
    message: "The kitchen is busy. Try again in a moment.",
    action: "Try again",
  },
  llm_unavailable: { message: "Can't reach the chef right now.", action: "Try again" },
  llm_output_invalid: { message: "The proposal came back garbled.", action: "Try again" },
  could_not_satisfy: {
    message: "Couldn't fit a meal to your pantry after 3 tries.",
    action: "Simplify sentence",
  },
  too_many_attempts: { message: "This one isn't converging.", action: "Start over" },
  stale_proposal: {
    message: "Your pantry changed since this was proposed.",
    action: "Re-propose",
  },
  interrupted_by_restart: { message: "This session was interrupted.", action: "Start again" },
  empty_pantry: {
    message: "The pantry is empty. Add items before cooking.",
    action: "Add items",
  },
  network: {
    message: "Couldn't reach the kitchen. Check that the server is running.",
    action: "Retry",
  },
};

export function cookErrorPresentation(
  code: string | undefined,
  detail: string | undefined,
): { message: string; action: string } {
  const known = code ? KNOWN_ERRORS[code] : undefined;
  if (known) return known;
  return {
    message: detail?.trim() || "The cook didn't come back with a meal.",
    action: "Start over",
  };
}

export function shoppingListText(
  lines: {
    kind: string;
    missing_name?: string | null;
    missing_note?: string | null;
    item_name?: string;
  }[],
): string {
  return lines
    .filter((line) => line.kind === "missing")
    .map((line) => {
      const name = line.missing_name || line.item_name || "ingredient";
      return line.missing_note ? `${name} — ${line.missing_note}` : name;
    })
    .join("\n");
}

export function retriesSameSentence(action: string): boolean {
  return action === "Try again" || action === "Start again" || action === "Retry";
}
