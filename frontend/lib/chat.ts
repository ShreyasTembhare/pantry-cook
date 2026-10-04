import { ApiError, type ChatCard, type ChatMessage } from "@/lib/api";
import { cookErrorPresentation } from "@/lib/cook";

/**
 * The confirmation that is still waiting on the user. Confirming or cancelling
 * appends a newer assistant message, so only the latest one can be open.
 */
export function openPendingCard(messages: ChatMessage[]): ChatCard | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "assistant") continue;
    return message.cards.find((card) => card.type === "pending" && card.pending_id) ?? null;
  }
  return null;
}

/** The one recipe card that may still be confirmed. Older copies stay readable. */
export function liveCookCardKey(
  messages: ChatMessage[],
  activeCookSessionId: string | null,
): string | null {
  if (!activeCookSessionId) return null;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message || message.role !== "assistant") continue;
    for (let cardIndex = message.cards.length - 1; cardIndex >= 0; cardIndex -= 1) {
      const card = message.cards[cardIndex];
      if (!card?.proposal) continue;
      if (card.type !== "proposal" && card.pending_kind !== "confirm_cook") continue;
      if (card.cook_session_id && card.cook_session_id !== activeCookSessionId) continue;
      return `${message.id}:${cardIndex}`;
    }
  }
  return null;
}

export function pendingSummary(card: ChatCard): string {
  if (card.pending_kind === "delete_item") {
    const name = card.items[0]?.name;
    return name ? `Remove ${name} from the pantry?` : card.title;
  }
  if (card.pending_kind === "undo_meal") {
    return card.meal ? `Undo ${card.meal.title}?` : card.title;
  }
  return card.proposal ? `Cook ${card.proposal.title}?` : card.title;
}

export function sendFailure(error: unknown): { message: string; action: string } {
  if (error instanceof ApiError) {
    return cookErrorPresentation(error.problem.code, error.problem.detail);
  }
  return { message: "Pip couldn't reply. Try again.", action: "Try again" };
}
