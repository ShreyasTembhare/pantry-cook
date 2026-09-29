import { format } from "date-fns";

import { addDaysISO, parseISODate } from "@/lib/pantry";

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

/** A blank cook sentence. The parse node turns it into the soonest-expiring items. */
export const EXPIRING_COOK_SENTENCE = "";

export const EXPIRING_COOK_LABEL = "What's expiring";

export function displayCookSentence(sentence: string): string {
  return sentence.trim() || "Cook what's expiring";
}

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

export function rateLimitMessage(retryAfter: number | null | undefined): string {
  if (retryAfter === null || retryAfter === undefined || !Number.isFinite(retryAfter) || retryAfter <= 0) {
    return "The kitchen is busy. Try again in a moment.";
  }
  const seconds = Math.max(1, Math.ceil(retryAfter));
  return `The kitchen is busy. Try again in ${seconds}s.`;
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
  checkpoint_unreadable: { message: "This session was interrupted.", action: "Start again" },
  expired_unacknowledged: {
    message: "This proposal uses food that's already expired.",
    action: "Re-propose",
  },
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
  retryAfter?: number | null,
): { message: string; action: string } {
  if (code === "llm_rate_limited") {
    return { message: rateLimitMessage(retryAfter), action: "Try again" };
  }
  const known = code ? KNOWN_ERRORS[code] : undefined;
  if (known) return known;
  return {
    message: detail?.trim() || "The cook didn't come back with a meal.",
    action: "Start over",
  };
}

export function expiredAcknowledgement(
  lines: { kind: string; item_id?: string }[],
  pantry: Record<string, { name: string; expires_on?: string | null }>,
  today: string,
): string | null {
  const parts: string[] = [];
  for (const line of lines) {
    if (line.kind !== "use" || !line.item_id) continue;
    const item = pantry[line.item_id];
    if (!item?.expires_on || item.expires_on >= today) continue;
    const weekday = format(parseISODate(item.expires_on), "EEEE");
    parts.push(`the ${item.name.toLocaleLowerCase()} expired ${weekday}`);
  }
  if (parts.length === 0) return null;
  if (parts.length === 1) return `I know ${parts[0]}`;
  const last = parts[parts.length - 1];
  return `I know ${parts.slice(0, -1).join(", ")} and ${last}`;
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

export const REVISION_ORDER_LABEL = "Oldest first";

export type RevisionAttempt = {
  attempt_no: number;
  trigger: "initial" | "auto_repair" | "user_revision";
  user_note: string | null;
  proposal: { title: string; steps?: string[] } | null;
};

export type RevisionEntry = {
  attemptNo: number;
  triggerLabel: string;
  title: string;
  opening: string | null;
  note: string | null;
};

const TRIGGER_LABEL: Record<RevisionAttempt["trigger"], string> = {
  initial: "First proposal",
  auto_repair: "Adjusted",
  user_revision: "Revised",
};

function shortLine(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length <= 90) return trimmed;
  return `${trimmed.slice(0, 87).trimEnd()}…`;
}

/** Checkpoint attempts, oldest first, with the note that produced a revision. */
export function revisionHistory(attempts: RevisionAttempt[]): RevisionEntry[] {
  return [...attempts]
    .sort((a, b) => a.attempt_no - b.attempt_no)
    .map((attempt) => {
      const title = attempt.proposal?.title?.trim() || "No meal came back";
      const firstStep = attempt.proposal?.steps?.find((step) => step.trim());
      const note =
        attempt.trigger === "user_revision" && attempt.user_note?.trim()
          ? attempt.user_note.trim()
          : null;
      return {
        attemptNo: attempt.attempt_no,
        triggerLabel: TRIGGER_LABEL[attempt.trigger],
        title,
        opening: firstStep ? shortLine(firstStep) : null,
        note,
      };
    });
}
