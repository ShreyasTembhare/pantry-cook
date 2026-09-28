import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DuplicatePrompt } from "@/components/pantry/duplicate-prompt";

describe("DuplicatePrompt", () => {
  it("offers to add onto an item in the same measure", async () => {
    const user = userEvent.setup();
    const onMerge = vi.fn();
    const onRename = vi.fn();
    render(
      <DuplicatePrompt
        name="Rice"
        quantity="200"
        unit="g"
        sameDimension
        onMerge={onMerge}
        onRename={onRename}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Rice is already in the pantry.");
    await user.click(screen.getByRole("button", { name: "Add 200 g to it" }));
    expect(onMerge).toHaveBeenCalledOnce();
  });

  it("only offers a rename when the measure differs", async () => {
    const user = userEvent.setup();
    const onRename = vi.fn();
    render(
      <DuplicatePrompt
        name="Milk"
        quantity="200"
        unit="g"
        sameDimension={false}
        onMerge={vi.fn()}
        onRename={onRename}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("different measure");
    expect(screen.queryByRole("button", { name: /Add / })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rename" }));
    expect(onRename).toHaveBeenCalledOnce();
  });
});
