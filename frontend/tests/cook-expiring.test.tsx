import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CookStart } from "@/components/cook/cook-start";
import { listItems, startCook, type Item } from "@/lib/api";

const push = vi.fn();

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listItems: vi.fn(),
    startCook: vi.fn(),
  };
});

function item(partial: Partial<Item> & Pick<Item, "id" | "name" | "expires_on">): Item {
  return {
    quantity: "200",
    unit: "g",
    dimension: "mass",
    version: 1,
    created_at: "2026-09-28T00:00:00",
    updated_at: "2026-09-28T00:00:00",
    ...partial,
  };
}

function renderCook() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CookStart />
    </QueryClientProvider>,
  );
}

describe("cook what's expiring", () => {
  beforeEach(() => {
    push.mockReset();
    vi.mocked(listItems).mockReset();
    vi.mocked(startCook).mockReset();
    vi.mocked(startCook).mockResolvedValue({ id: "sess-expiring" } as never);
  });

  it("submits a blank sentence from the chip and from an empty box", async () => {
    const user = userEvent.setup();
    vi.mocked(listItems).mockResolvedValue([
      item({ id: "spinach", name: "Spinach", expires_on: "2026-09-30" }),
      item({ id: "rice", name: "Rice", expires_on: null }),
    ]);

    renderCook();

    const chip = await screen.findByRole("button", { name: "What's expiring" });
    await user.click(chip);

    await waitFor(() => {
      expect(startCook).toHaveBeenCalledWith("", { defer: true });
    });
    expect(push).toHaveBeenCalledWith("/cook/sess-expiring");

    vi.mocked(startCook).mockClear();
    push.mockClear();
    await user.clear(screen.getByRole("textbox", { name: "What do you want to cook?" }));
    await user.click(screen.getByRole("button", { name: "Propose" }));

    await waitFor(() => {
      expect(startCook).toHaveBeenCalledWith("", { defer: true });
    });
  });

  it("keeps the empty-pantry explanation when nothing is in the pantry", async () => {
    vi.mocked(listItems).mockResolvedValue([]);
    renderCook();

    expect(await screen.findByText(/The pantry is empty/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "What's expiring" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Propose" })).not.toBeInTheDocument();
    expect(startCook).not.toHaveBeenCalled();
  });
});
