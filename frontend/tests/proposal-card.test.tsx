import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProposalCard, type ProposalView } from "@/components/cook/proposal-card";

const proposal: ProposalView = {
  title: "Chicken and leeks",
  servings: 2,
  rationale: "Uses the chicken while it is still good.",
  lines: [
    { kind: "use", item_id: "chicken", quantity: "200", unit: "g" },
    { kind: "missing", name: "olive oil", quantity_note: "a splash" },
  ],
  steps: ["Prep the chicken.", "Cook gently until just done."],
};

const pantry = {
  chicken: { name: "Chicken", quantity: "400", unit: "g" },
};

function renderCard(overrides: Partial<React.ComponentProps<typeof ProposalCard>> = {}) {
  const onConfirm = vi.fn();
  const onRevise = vi.fn();
  const onAbandon = vi.fn();
  const onRepropose = vi.fn();
  render(
    <ProposalCard
      proposal={proposal}
      pantry={pantry}
      onConfirm={onConfirm}
      onRevise={onRevise}
      onAbandon={onAbandon}
      onRepropose={onRepropose}
      {...overrides}
    />,
  );
  return { onConfirm, onRevise, onAbandon, onRepropose };
}

describe("ProposalCard", () => {
  it("renders the title, a use line with a depletion bar, a missing line, and steps", () => {
    renderCard();
    expect(screen.getByRole("heading", { name: "Chicken and leeks" })).toBeInTheDocument();
    expect(screen.getByText("2 servings")).toBeInTheDocument();
    expect(screen.getByText("Uses the chicken while it is still good.")).toBeInTheDocument();
    expect(screen.getByText("Chicken")).toBeInTheDocument();
    expect(screen.getByText("200 g of 400 g")).toBeInTheDocument();
    expect(screen.getByTestId("depletion-chicken")).toHaveStyle({ width: "50%" });
    const missing = screen.getByRole("region", { name: "Missing" });
    expect(missing).toHaveTextContent("olive oil");
    expect(missing).toHaveTextContent("a splash");
    expect(screen.getByText("Prep the chicken.")).toBeInTheDocument();
  });

  it("renders a partial proposal without inventing steps", () => {
    renderCard({
      proposal: {
        title: "Half a thought",
        lines: [{ kind: "use", item_id: "rice", quantity: "1", unit: "count" }],
      },
      pantry: { rice: { name: "Rice", quantity: "2", unit: "count" } },
    });
    expect(screen.getByRole("heading", { name: "Half a thought" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Steps" })).not.toBeInTheDocument();
    expect(screen.queryByText(/servings/)).not.toBeInTheDocument();
  });

  it("confirms, revises, and abandons from the footer", async () => {
    const user = userEvent.setup();
    const { onConfirm, onRevise, onAbandon } = renderCard({ attemptLabel: "Attempt 2" });

    expect(screen.getByText("Attempt 2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "Revise" }));
    const note = screen.getByRole("textbox", { name: "Revision note" });
    await user.type(note, "fewer steps");
    await user.click(screen.getByRole("button", { name: "Send revision" }));
    expect(onRevise).toHaveBeenCalledWith("fewer steps");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Abandon" }));
    await user.click(screen.getByRole("button", { name: "Yes, abandon" }));
    expect(onAbandon).toHaveBeenCalledOnce();
  });

  it("uses C to confirm, R to revise, and Escape to cancel", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderCard();

    await user.keyboard("c");
    expect(onConfirm).toHaveBeenCalledOnce();

    await user.keyboard("r");
    const note = screen.getByRole("textbox", { name: "Revision note" });
    expect(note).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("textbox", { name: "Revision note" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
  });

  it("asks before confirming an expired ingredient", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderCard({
      today: "2026-09-28",
      pantry: {
        chicken: { name: "Yoghurt", quantity: "400", unit: "g", expires_on: "2026-09-21" },
      },
      proposal: {
        title: "Yoghurt on a plate",
        servings: 2,
        lines: [{ kind: "use", item_id: "chicken", quantity: "200", unit: "g" }],
        steps: ["Stir it."],
      },
    });

    expect(
      screen.getByRole("checkbox", { name: "I know the yoghurt expired Monday" }),
    ).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    await user.keyboard("c");
    expect(onConfirm).not.toHaveBeenCalled();

    await user.click(screen.getByRole("checkbox", { name: "I know the yoghurt expired Monday" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledWith(true);
  });

  it("shows a stale banner and disables confirm until a re-propose", async () => {
    const user = userEvent.setup();
    const { onConfirm, onRepropose } = renderCard({ stale: true });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Your pantry changed since this was proposed.",
    );
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    await user.keyboard("c");
    expect(onConfirm).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Re-propose" }));
    expect(onRepropose).toHaveBeenCalledOnce();
  });
});
