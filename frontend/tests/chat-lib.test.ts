import { describe, expect, it } from "vitest";

import { ApiError, type ChatCard, type ChatMessage } from "@/lib/api";
import { liveCookCardKey, openPendingCard, pendingSummary, sendFailure } from "@/lib/chat";

function card(partial: Partial<ChatCard>): ChatCard {
  return { type: "note", title: "x", items: [], meals: [], ...partial } as ChatCard;
}

function message(role: ChatMessage["role"], cards: ChatCard[] = []): ChatMessage {
  return { id: `${role}-${cards.length}-${Math.random()}`, role, content: "hi", cards, created_at: "" };
}

const deleteCard = card({
  type: "pending",
  title: "Remove Leeks?",
  pending_id: "p1",
  pending_kind: "delete_item",
  items: [
    {
      id: "i1",
      name: "Leeks",
      quantity: "2",
      unit: "count",
      dimension: "count",
      expires_on: null,
      version: 1,
      created_at: "",
      updated_at: "",
    },
  ],
});

describe("openPendingCard", () => {
  it("finds the confirmation in the latest assistant message", () => {
    const messages = [message("user"), message("assistant", [deleteCard])];
    expect(openPendingCard(messages)?.pending_id).toBe("p1");
  });

  it("treats a confirmation as closed once a newer assistant message exists", () => {
    const messages = [
      message("assistant", [deleteCard]),
      message("user"),
      message("assistant", [card({ title: "Removed Leeks." })]),
    ];
    expect(openPendingCard(messages)).toBeNull();
  });

  it("is null for an empty thread", () => {
    expect(openPendingCard([])).toBeNull();
  });
});

describe("liveCookCardKey", () => {
  it("keeps only the newest recipe for the open meal", () => {
    const older = card({
      type: "proposal",
      title: "Old",
      proposal: { title: "Old soup", servings: 1, lines: [], steps: [] },
      cook_session_id: "s1",
    });
    const newer = card({
      type: "proposal",
      title: "New",
      proposal: { title: "New soup", servings: 1, lines: [], steps: [] },
      cook_session_id: "s1",
    });
    const messages = [
      { id: "a1", role: "assistant" as const, content: "first", cards: [older], created_at: "" },
      { id: "a2", role: "assistant" as const, content: "next", cards: [newer], created_at: "" },
    ];
    expect(liveCookCardKey(messages, "s1")).toBe("a2:0");
    expect(liveCookCardKey(messages, null)).toBeNull();
    expect(liveCookCardKey(messages, "other")).toBeNull();
  });
});

describe("pendingSummary", () => {
  it("names what will change", () => {
    expect(pendingSummary(deleteCard)).toBe("Remove Leeks from the pantry?");
    expect(pendingSummary(card({ pending_kind: "undo_meal", title: "Undo it?" }))).toBe("Undo it?");
  });
});

describe("sendFailure", () => {
  it("maps API problem codes to kitchen wording", () => {
    const error = new ApiError({
      type: "about:blank",
      title: "t",
      status: 0,
      detail: "offline",
      instance: "/api/chat/messages",
      code: "network",
      request_id: "r",
    });
    expect(sendFailure(error)).toEqual({
      message: "Couldn't reach the kitchen. Check that the server is running.",
      action: "Retry",
    });
  });

  it("falls back for unknown errors", () => {
    expect(sendFailure(new Error("boom")).message).toBe("Pip couldn't reply. Try again.");
  });
});
