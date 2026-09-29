import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RevisionTimeline } from "@/components/cook/revision-timeline";
import type { RevisionAttempt } from "@/lib/cook";

const attempts: RevisionAttempt[] = [
  {
    attempt_no: 2,
    trigger: "user_revision",
    user_note: "fewer steps",
    proposal: {
      title: "Leeks and eggs",
      steps: ["Cook everything in one pan and serve."],
    },
  },
  {
    attempt_no: 1,
    trigger: "initial",
    user_note: null,
    proposal: { title: "Leek skillet", steps: ["Prep the leeks."] },
  },
];

describe("RevisionTimeline", () => {
  it("lists what was proposed, oldest first, with the revise note", () => {
    render(<RevisionTimeline attempts={attempts} />);

    expect(
      screen.getByRole("region", { name: "Revision history, oldest first" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Oldest first")).toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Attempt 1");
    expect(items[0]).toHaveTextContent("First proposal");
    expect(items[0]).toHaveTextContent("Leek skillet");
    expect(items[0]).toHaveTextContent("Prep the leeks.");
    expect(items[1]).toHaveTextContent("Attempt 2");
    expect(items[1]).toHaveTextContent("Revised");
    expect(items[1]).toHaveTextContent("fewer steps");
    expect(items[1]).toHaveTextContent("Leeks and eggs");
    expect(items[1]).toHaveTextContent("Cook everything in one pan and serve.");
    expect(items[1]).toHaveAttribute("aria-current", "step");
  });

  it("renders nothing when the graph has no attempts yet", () => {
    const { container } = render(<RevisionTimeline attempts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
