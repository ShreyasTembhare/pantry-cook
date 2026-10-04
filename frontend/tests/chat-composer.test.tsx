import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatComposer } from "@/components/chat/chat-composer";

describe("ChatComposer", () => {
  it("sends on Enter and keeps Shift+Enter for new lines", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer busy={false} suggestions={[]} onSend={onSend} />);
    const box = screen.getByRole("textbox", { name: "Message Pip" });
    await user.type(box, "hello{Shift>}{Enter}{/Shift}there");
    expect(onSend).not.toHaveBeenCalled();
    await user.type(box, "{Enter}");
    expect(onSend).toHaveBeenCalledWith("hello\nthere");
    expect(box).toHaveValue("");
  });

  it("will not send blank text or while busy", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const { rerender } = render(<ChatComposer busy={false} suggestions={[]} onSend={onSend} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    rerender(<ChatComposer busy suggestions={["a chip"]} onSend={onSend} />);
    await user.click(screen.getByRole("button", { name: "a chip" }));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("sends a suggestion whole and labels the chip group", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(
      <ChatComposer busy={false} suggestions={["Something with the spinach"]} onSend={onSend} />,
    );
    expect(screen.getByRole("group", { name: "Suggested messages" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Something with the spinach" }));
    expect(onSend).toHaveBeenCalledWith("Something with the spinach");
  });

  it("falls back to examples and offers a retry when the pantry fails to load", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <ChatComposer
        busy={false}
        suggestions={[]}
        pantryState="error"
        onRetryPantry={onRetry}
        onSend={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "What's in the pantry?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("points an empty pantry at the pantry page", () => {
    render(<ChatComposer busy={false} suggestions={[]} pantryState="empty" onSend={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Add items" })).toHaveAttribute("href", "/pantry");
  });
});
