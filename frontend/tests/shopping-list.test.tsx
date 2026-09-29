import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ShoppingList } from "@/components/meals/shopping-list";
import { getMeal, type Meal, type MealLine } from "@/lib/api";

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

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ShoppingList id="meal-1" />
    </QueryClientProvider>,
  );
}

describe("shopping list", () => {
  beforeEach(() => {
    vi.mocked(getMeal).mockReset();
  });

  it("lists the missing ingredients and leaves out what the pantry already covered", async () => {
    vi.mocked(getMeal).mockResolvedValue(
      meal([
        line({
          id: "use-chicken",
          kind: "use",
          item_id: "item-chicken",
          item_name: "Chicken",
          quantity: "200",
          unit: "g",
          position: 0,
        }),
        line({
          id: "miss-butter",
          kind: "missing",
          item_name: "butter",
          missing_name: "butter",
          missing_note: "200 g",
          position: 1,
        }),
        line({
          id: "miss-oil",
          kind: "missing",
          item_name: "olive oil",
          missing_name: "olive oil",
          missing_note: "a splash",
          position: 2,
        }),
      ]),
    );

    renderList();

    const list = await screen.findByRole("list", { name: "Shopping list" });
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("butter");
    expect(items[0]).toHaveTextContent("200 g");
    expect(items[1]).toHaveTextContent("olive oil");
    expect(items[1]).toHaveTextContent("a splash");
    expect(list).not.toHaveTextContent("Chicken");
    expect(screen.getByRole("heading", { name: "Leeks and eggs" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "butter, 200 g" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "olive oil, a splash" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Print" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Meal" })).toHaveAttribute("href", "/meals/meal-1");
  });
});
