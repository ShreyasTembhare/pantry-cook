import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatHome } from "@/components/chat/chat-home";
import {
  ApiError,
  getChat,
  listItems,
  sendChatMessage,
  type ChatThread,
  type ChatTurn,
} from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getChat: vi.fn(),
    listItems: vi.fn(),
    sendChatMessage: vi.fn(),
    confirmChatPending: vi.fn(),
    cancelChatPending: vi.fn(),
  };
});

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const empty: ChatThread = { id: "t1", active_cook_session_id: null, messages: [] };

function turn(text: string, reply: string): ChatTurn {
  return {
    thread_id: "t1",
    user: { id: `u-${text}`, role: "user", content: text, cards: [], created_at: "" },
    assistant: { id: `a-${text}`, role: "assistant", content: reply, cards: [], created_at: "" },
  };
}

function networkError() {
  return new ApiError({
    type: "about:blank",
    title: "Network error",
    status: 0,
    detail: "offline",
    instance: "/api/chat/messages",
    code: "network",
    request_id: "r",
  });
}

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatHome />
    </QueryClientProvider>,
  );
}

// The server keeps every turn, so a refetch after a send must return it.
let stored: ChatThread = empty;

function serverReplies(text: string, reply: string) {
  return async () => {
    const next = turn(text, reply);
    stored = { ...stored, messages: [...stored.messages, next.user, next.assistant] };
    return next;
  };
}

describe("ChatHome", () => {
  beforeEach(() => {
    stored = empty;
    vi.mocked(getChat)
      .mockReset()
      .mockImplementation(async () => stored);
    vi.mocked(listItems).mockReset().mockResolvedValue([]);
    vi.mocked(sendChatMessage).mockReset();
  });

  it("welcomes an empty thread and nudges an empty pantry", async () => {
    renderHome();
    expect(await screen.findByText("What should we cook?")).toBeInTheDocument();
    expect(await screen.findByText(/The pantry is empty\./)).toBeInTheDocument();
  });

  it("shows the sent message and the reply in a labelled log", async () => {
    const user = userEvent.setup();
    vi.mocked(sendChatMessage).mockImplementation(serverReplies("hello", "Hi there."));
    renderHome();
    await screen.findByText("What should we cook?");
    await user.type(screen.getByRole("textbox", { name: "Message Pip" }), "hello{Enter}");
    expect(await screen.findByText("Hi there.")).toBeInTheDocument();
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log).toHaveTextContent("hello");
    expect(log).toHaveTextContent("Hi there.");
  });

  it("keeps a failed message visible and retries it", async () => {
    const user = userEvent.setup();
    vi.mocked(sendChatMessage)
      .mockRejectedValueOnce(networkError())
      .mockImplementationOnce(serverReplies("2 leeks", "Adding that to the pantry."));
    renderHome();
    await screen.findByText("What should we cook?");
    await user.type(screen.getByRole("textbox", { name: "Message Pip" }), "2 leeks{Enter}");

    expect(await screen.findByText("Not sent")).toBeInTheDocument();
    expect(screen.getByText("2 leeks")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Couldn't reach the kitchen. Check that the server is running.",
    );

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Adding that to the pantry.")).toBeInTheDocument();
    expect(sendChatMessage).toHaveBeenCalledTimes(2);
    expect(sendChatMessage).toHaveBeenLastCalledWith("2 leeks");
    await waitFor(() => expect(screen.queryByText("Not sent")).not.toBeInTheDocument());
  });

  it("lets the user dismiss a failed message", async () => {
    const user = userEvent.setup();
    vi.mocked(sendChatMessage).mockRejectedValue(networkError());
    renderHome();
    await screen.findByText("What should we cook?");
    await user.type(screen.getByRole("textbox", { name: "Message Pip" }), "hello{Enter}");
    await user.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Not sent")).not.toBeInTheDocument();
  });

  it("shows the meal in progress and the open question above the thread", async () => {
    vi.mocked(getChat).mockResolvedValue({
      id: "t1",
      active_cook_session_id: "s1",
      messages: [
        {
          id: "a1",
          role: "assistant",
          content: "Remove them?",
          created_at: "",
          cards: [
            {
              type: "pending",
              title: "Remove Leeks?",
              pending_id: "p1",
              pending_kind: "delete_item",
              items: [],
              meals: [],
            },
          ],
        },
      ],
    });
    renderHome();
    expect(await screen.findByRole("link", { name: "Open in Cook" })).toHaveAttribute(
      "href",
      "/cook/s1",
    );
    expect(screen.getByRole("status", { name: "Conversation status" })).toHaveTextContent(
      "Waiting for you",
    );
  });
});
