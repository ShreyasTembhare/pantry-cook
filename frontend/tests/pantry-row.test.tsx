import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PantryRow } from "@/components/pantry/pantry-row";
import type { Item } from "@/lib/api";

vi.mock("@number-flow/react", () => ({
  default: ({ value, suffix }: { value: number; suffix?: string }) => (
    <span>
      {value}
      {suffix}
    </span>
  ),
}));

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: "item-1",
    name: "Yoghurt",
    quantity: "500",
    unit: "g",
    dimension: "mass",
    expires_on: "2026-09-26",
    version: 1,
    created_at: "2026-09-01T00:00:00",
    updated_at: "2026-09-01T00:00:00",
    ...overrides,
  };
}

const today = "2026-09-28";

function renderRow(row: Item, props: Partial<React.ComponentProps<typeof PantryRow>> = {}) {
  const onStartEdit = vi.fn();
  const onCancelEdit = vi.fn();
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onDelete = vi.fn().mockResolvedValue(undefined);
  render(
    <PantryRow
      item={row}
      today={today}
      editing={false}
      onStartEdit={onStartEdit}
      onCancelEdit={onCancelEdit}
      onSave={onSave}
      onDelete={onDelete}
      {...props}
    />,
  );
  return { onStartEdit, onCancelEdit, onSave, onDelete };
}

describe("PantryRow", () => {
  it("shows an expired chip and a relative date", () => {
    renderRow(item());
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getByText("Sat, 2 days ago")).toBeInTheDocument();
    expect(screen.getByTestId("quantity")).toHaveTextContent("500");
    expect(screen.getByTestId("quantity")).toHaveTextContent("g");
  });

  it("shows a use-soon chip for items inside three days", () => {
    renderRow(item({ expires_on: "2026-09-30", name: "Leeks" }));
    expect(screen.getByText("Use soon")).toBeInTheDocument();
    expect(screen.getByText("Wed, in 2 days")).toBeInTheDocument();
    expect(screen.queryByText("Expired")).not.toBeInTheDocument();
  });

  it("marks a zero quantity as out", () => {
    renderRow(item({ quantity: "0", expires_on: null, name: "Rice", unit: "g" }));
    expect(screen.getByText("Out")).toBeInTheDocument();
    expect(screen.getByText("No date")).toBeInTheDocument();
  });

  it("offers edit and delete, and confirms before removing", async () => {
    const user = userEvent.setup();
    const { onStartEdit, onDelete } = renderRow(item());

    await user.click(screen.getByRole("button", { name: "Actions for Yoghurt" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(onStartEdit).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "Actions for Yoghurt" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(screen.getByRole("dialog", { name: "Remove Yoghurt?" })).toBeInTheDocument();
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("saves an inline edit", async () => {
    const user = userEvent.setup();
    const { onSave } = renderRow(item({ name: "Leeks", quantity: "300" }), { editing: true });

    const name = screen.getByLabelText("Name");
    expect(name).toHaveValue("Leeks");
    await user.clear(name);
    await user.type(name, "Spring leeks");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledWith({
      name: "Spring leeks",
      quantity: "300",
      unit: "g",
      expires_on: "2026-09-26",
    });
  });
});
