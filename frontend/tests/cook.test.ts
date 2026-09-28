import { describe, expect, it } from "vitest";

import { cookErrorPresentation, shoppingListText, suggestionChips } from "@/lib/cook";

const today = "2026-09-28";

describe("suggestion chips", () => {
  it("offers a use-before-it-goes-off prompt for the soonest item", () => {
    const chips = suggestionChips(
      [
        { id: "1", name: "Chicken", quantity: "400", expires_on: "2026-09-30" },
        { id: "2", name: "Leeks", quantity: "300", expires_on: "2026-10-02" },
        { id: "3", name: "Rice", quantity: "500", expires_on: null },
      ],
      today,
    );

    expect(chips.map((chip) => chip.sentence)).toEqual([
      "use the chicken before it goes off",
      "something quick with the chicken and leeks before they turn",
      "something warm with the chicken",
    ]);
  });

  it("skips empty stock", () => {
    expect(
      suggestionChips([{ id: "1", name: "Salt", quantity: "0", expires_on: "2026-09-29" }], today),
    ).toEqual([]);
  });
});

describe("cook errors and shopping lists", () => {
  it("maps a failed proposal to a recovery action", () => {
    expect(cookErrorPresentation("could_not_satisfy", "raw")).toEqual({
      message: "Couldn't fit a meal to your pantry after 3 tries.",
      action: "Simplify sentence",
    });
    expect(cookErrorPresentation("stale_proposal", undefined).action).toBe("Re-propose");
  });

  it("copies missing lines as a shopping list", () => {
    expect(
      shoppingListText([
        { kind: "use", item_name: "Chicken" },
        { kind: "missing", missing_name: "olive oil", missing_note: "a splash" },
        { kind: "missing", missing_name: "lemon", missing_note: null },
      ]),
    ).toBe("olive oil \u2014 a splash\nlemon");
  });
});
