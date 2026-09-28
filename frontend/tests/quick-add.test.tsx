import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QuickAdd } from "@/components/pantry/quick-add";

describe("QuickAdd", () => {
  it("submits on Enter and returns focus to the name", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<QuickAdd onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Name"), "Rice");
    await user.type(screen.getByLabelText("Quantity"), "500");
    await user.keyboard("{Enter}");

    expect(onSubmit).toHaveBeenCalledWith({
      name: "Rice",
      quantity: "500",
      unit: "g",
      expires_on: "",
    });
    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("Name")).toHaveFocus();
  });

  it("clears the fields on Escape", async () => {
    const user = userEvent.setup();
    render(<QuickAdd onSubmit={vi.fn()} />);

    await user.type(screen.getByLabelText("Name"), "Milk");
    await user.type(screen.getByLabelText("Quantity"), "1");
    await user.keyboard("{Escape}");

    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("Quantity")).toHaveValue("");
    expect(screen.getByLabelText("Name")).toHaveFocus();
  });

  it("shows validation messages and does not submit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<QuickAdd onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByText("Name the item.")).toBeInTheDocument();
    expect(screen.getByText("Enter a quantity.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Name"), "Eggs");
    await user.type(screen.getByLabelText("Quantity"), "-2");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByText("Quantity cannot be negative.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
