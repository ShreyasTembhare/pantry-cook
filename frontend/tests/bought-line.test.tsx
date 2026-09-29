import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MealDetail } from "@/components/meals/meal-detail";
import { buyMissingLine, getMeal, type Meal, type MealLine } from "@/lib/api";

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
    buyMissingLine: vi.fn(),
  };
});

function line(partial: Partial<MealLine> & Pick<MealLine, "id" | "kind">): MealLine {
  return {
    item_id: null,
    item_name: partial.missing_name ?? "ingredient",
    quantity: null,
    unit: null,
    missing_name: null,
    missing_note: null,
    position: 0,
    ...partial,
  };
}

function meal(lines: MealLine[]): Meal {
  return {
    id: "meal-1",
    title: "Leeks and eggs",
    sentence: "something warm with the leeks",
    servings: 2,
    status: "cooked",
    cooked_at: "2026-09-28T12:00:00",
    created_at: "2026-09-28T12:00:00",
    use_count: 1,
    missing_count: lines.filter((row) => row.kind === "missing").length,
    steps: ["Cook gently until just done."],
    lines,
    cook_session_id: "session-1",
  };
}

const butter = line({
  id: "miss-butter",
  kind: "missing",
  item_name: "butter",
  missing_name: "butter",
  missing_note: "200 g",
  position: 1,
});

const oil = line({
  id: "miss-oil",
  kind: "missing",
  item_name: "olive oil",
  missing_name: "olive oil",
  missing_note: "a splash",
  position: 2,
});

function renderMeal() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MealDetail id="meal-1" />
    </QueryClientProvider>,
  );
}

describe("I bought this", () => {
  beforeEach(() => {
    vi.mocked(getMeal).mockReset();
    vi.mocked(buyMissingLine).mockReset();
  });

  it("buys a missing line that already has a quantity", async () => {
    vi.mocked(getMeal).mockResolvedValue(meal([butter, oil]));
    vi.mocked(buyMissingLine).mockResolvedValue({
      meal: meal([oil]),
      item_id: "item-butter",
      item_name: "butter",
      quantity: "200",
      unit: "g",
      created: true,
    });
    const user = userEvent.setup();
    renderMeal();

    await user.click(await screen.findByRole("button", { name: "I bought this: butter" }));

    expect(buyMissingLine).toHaveBeenCalledTimes(1);
    expect(buyMissingLine).toHaveBeenCalledWith("meal-1", "miss-butter", {
      quantity: "200",
      unit: "g",
    });
    expect(screen.queryByLabelText("Quantity")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "I bought this: butter" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "I bought this: olive oil" })).toBeInTheDocument();
  });

  it("asks for a quantity when the missing line has none", async () => {
    vi.mocked(getMeal).mockResolvedValue(meal([butter, oil]));
    vi.mocked(buyMissingLine).mockResolvedValue({
      meal: meal([butter]),
      item_id: "item-oil",
      item_name: "olive oil",
      quantity: "250",
      unit: "g",
      created: true,
    });
    const user = userEvent.setup();
    renderMeal();

    await user.click(await screen.findByRole("button", { name: "I bought this: olive oil" }));

    expect(buyMissingLine).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Quantity")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add to pantry" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a quantity.");
    expect(buyMissingLine).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Quantity"), "250");
    await user.click(screen.getByRole("button", { name: "Add to pantry" }));

    expect(buyMissingLine).toHaveBeenCalledWith("meal-1", "miss-oil", {
      quantity: "250",
      unit: "g",
    });
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "I bought this: olive oil" }),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "I bought this: butter" })).toBeInTheDocument();
  });
});
