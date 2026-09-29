import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MealDetail } from "@/components/meals/meal-detail";
import { getMeal, undoMeal, type Meal } from "@/lib/api";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getMeal: vi.fn(),
    undoMeal: vi.fn(),
  };
});

function meal(status: string): Meal {
  return {
    id: "meal-1",
    title: "Leeks and eggs",
    sentence: "something warm with the leeks",
    servings: 2,
    status,
    cooked_at: "2026-09-28T12:00:00",
    created_at: "2026-09-28T12:00:00",
    use_count: 1,
    missing_count: 0,
    steps: ["Cook gently until just done."],
    lines: [
      {
        id: "line-1",
        kind: "use",
        item_id: "item-1",
        item_name: "Leeks",
        quantity: "150",
        unit: "g",
        missing_name: null,
        missing_note: null,
        position: 0,
      },
    ],
    cook_session_id: "session-1",
  };
}

function renderMeal() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MealDetail id="meal-1" />
    </QueryClientProvider>,
  );
}

describe("meal undo", () => {
  beforeEach(() => {
    vi.mocked(getMeal).mockReset();
    vi.mocked(undoMeal).mockReset();
  });

  it("shows Undo on /meals/[id] and restores once", async () => {
    vi.mocked(getMeal).mockResolvedValue(meal("cooked"));
    vi.mocked(undoMeal).mockResolvedValue(meal("undone"));
    const user = userEvent.setup();
    renderMeal();

    await user.click(await screen.findByRole("button", { name: /^Undo$/ }));
    expect(screen.getByRole("dialog", { name: "Undo this meal?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo meal" }));

    expect(undoMeal).toHaveBeenCalledTimes(1);
    expect(undoMeal).toHaveBeenCalledWith("meal-1");
    expect(await screen.findByRole("status")).toHaveTextContent("Undone.");
    expect(screen.queryByRole("button", { name: /^Undo$/ })).not.toBeInTheDocument();
  });

  it("does not offer Undo when the meal is already undone", async () => {
    vi.mocked(getMeal).mockResolvedValue(meal("undone"));
    renderMeal();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "The quantities this meal used are back in the pantry.",
    );
    expect(screen.queryByRole("button", { name: /^Undo$/ })).not.toBeInTheDocument();
    expect(undoMeal).not.toHaveBeenCalled();
  });
});
