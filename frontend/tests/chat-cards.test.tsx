import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatCards } from "@/components/chat/chat-cards";
import { ChatStatus } from "@/components/chat/chat-status";
import type { ChatCard } from "@/lib/api";

const leeks = {
  id: "i1",
  name: "Leeks",
  quantity: "2",
  unit: "count" as const,
  dimension: "count" as const,
  expires_on: "2026-01-01",
  version: 1,
  created_at: "",
  updated_at: "",
};

function card(partial: Partial<ChatCard>): ChatCard {
  return { type: "note", title: "x", items: [], meals: [], ...partial } as ChatCard;
}

function renderCards(cards: ChatCard[], overrides: Partial<Parameters<typeof ChatCards>[0]> = {}) {
  const handlers = {
    onConfirmPending: vi.fn(),
    onCancelPending: vi.fn(),
    onRevise: vi.fn(),
    onAbandon: vi.fn(),
    onAskConfirm: vi.fn(),
  };
  render(<ChatCards cards={cards} pantry={[leeks]} busy={false} {...handlers} {...overrides} />);
  return handlers;
}

describe("pending cards", () => {
  it("shows the pantry row that a delete will remove", async () => {
    const user = userEvent.setup();
    const handlers = renderCards([
      card({
        type: "pending",
        title: "Remove Leeks?",
        pending_id: "p1",
        pending_kind: "delete_item",
        items: [leeks],
      }),
    ]);
    expect(screen.getByText("Remove Leeks?")).toBeInTheDocument();
    expect(screen.getByText(/2 count/)).toBeInTheDocument();
    expect(screen.getByText("This takes it out of the pantry for good.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(handlers.onConfirmPending).toHaveBeenCalledWith("p1", false);
    await user.click(screen.getByRole("button", { name: "Keep it" }));
    expect(handlers.onCancelPending).toHaveBeenCalledWith("p1");
  });

  it("explains what an undo restores and names the meal", () => {
    renderCards([
      card({
        type: "pending",
        title: "Undo Leek soup?",
        pending_id: "p2",
        pending_kind: "undo_meal",
        meal: { id: "m1", title: "Leek soup" } as ChatCard["meal"],
      }),
    ]);
    expect(screen.getByText("Leek soup")).toBeInTheDocument();
    expect(screen.getByText("The ingredients go back into the pantry.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo meal" })).toBeInTheDocument();
  });

  it("disables answers while busy", () => {
    renderCards(
      [card({ type: "pending", title: "Remove Leeks?", pending_id: "p1", pending_kind: "delete_item" })],
      { busy: true },
    );
    expect(screen.getByRole("button", { name: "Remove" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Keep it" })).toBeDisabled();
  });
});

describe("recipe cards", () => {
  it("leaves actions on the live recipe and keeps the older one as history", () => {
    renderCards(
      [
        card({
          type: "proposal",
          title: "Old",
          proposal: { title: "Old soup", servings: 1, lines: [], steps: [] },
          cook_session_id: "s1",
        }),
        card({
          type: "proposal",
          title: "New",
          proposal: { title: "New soup", servings: 1, lines: [], steps: [] },
          cook_session_id: "s1",
        }),
      ],
      { messageId: "m1", liveCookCardKey: "m1:1" },
    );
    expect(screen.getByRole("heading", { name: "Old soup" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "New soup" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Confirm" })).toHaveLength(1);
  });
});

describe("answered confirmations", () => {
  it("shows an older confirmation as history without buttons", () => {
    renderCards(
      [card({ type: "pending", title: "Remove Leeks?", pending_id: "old", pending_kind: "delete_item" })],
      { openPendingId: "newer" },
    );
    expect(screen.getByText("Remove Leeks? Already answered.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  });

  it("keeps the buttons on the confirmation that is still open", () => {
    renderCards(
      [card({ type: "pending", title: "Remove Leeks?", pending_id: "p1", pending_kind: "delete_item" })],
      { openPendingId: "p1" },
    );
    expect(screen.getByRole("button", { name: "Remove" })).toBeEnabled();
  });
});

describe("error and list cards", () => {
  it("maps an empty pantry error to a way forward", () => {
    renderCards([
      card({
        type: "error",
        title: "Your pantry is empty.",
        error: { code: "empty_pantry", detail: "Your pantry is empty." },
      }),
    ]);
    expect(screen.getByRole("alert")).toHaveTextContent("The pantry is empty. Add items before cooking.");
    expect(screen.getByRole("link", { name: "Add items" })).toHaveAttribute("href", "/pantry");
  });

  it("keeps the server detail for codes it does not know", () => {
    renderCards([
      card({
        type: "error",
        title: "Say how much to set it to.",
        error: { code: "quantity_required", detail: "Say how much to set it to." },
      }),
    ]);
    expect(screen.getByRole("alert")).toHaveTextContent("Say how much to set it to.");
  });

  it("links cooked meals", () => {
    renderCards([
      card({
        type: "meals",
        title: "Cooked meals",
        meals: [{ id: "m1", title: "Leek soup" } as ChatCard["meals"][number]],
      }),
    ]);
    expect(screen.getByRole("link", { name: "Leek soup" })).toHaveAttribute("href", "/meals/m1");
  });

  it("marks an expired pantry row", () => {
    renderCards([card({ type: "pantry", title: "In the pantry", items: [leeks] })]);
    expect(screen.getByText("Expired")).toBeInTheDocument();
  });
});

describe("ChatStatus", () => {
  it("renders nothing without a meal or a question", () => {
    const { container } = render(<ChatStatus cookSessionId={null} pending={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("links the meal in progress and states what Pip is waiting on", () => {
    render(
      <ChatStatus
        cookSessionId="s1"
        pending={card({
          type: "pending",
          title: "Remove Leeks?",
          pending_id: "p1",
          pending_kind: "delete_item",
          items: [leeks],
        })}
      />,
    );
    expect(screen.getByRole("status", { name: "Conversation status" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Cook" })).toHaveAttribute("href", "/cook/s1");
    expect(screen.getByText(/Remove Leeks from the pantry\?/)).toBeInTheDocument();
  });
});
