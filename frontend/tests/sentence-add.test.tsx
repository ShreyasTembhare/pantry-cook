import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SentenceAdd } from "@/components/pantry/sentence-add";
import { ApiError, previewPantrySentence, savePantrySentence, type Item } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    previewPantrySentence: vi.fn(),
    savePantrySentence: vi.fn(),
  };
});

const preview = {
  sentence: "2 leeks and 500 g chicken",
  items: [
    { name: "Leeks", quantity: "2", unit: "count" as const, action: "create" as const },
    { name: "Chicken", quantity: "500", unit: "g" as const, action: "create" as const },
  ],
};

const savedLeeks: Item = {
  id: "leeks",
  name: "Leeks",
  quantity: "2",
  unit: "count",
  dimension: "count",
  expires_on: null,
  version: 1,
  created_at: "2026-09-01T00:00:00",
  updated_at: "2026-09-01T00:00:00",
};

describe("SentenceAdd", () => {
  beforeEach(() => {
    vi.mocked(previewPantrySentence).mockReset();
    vi.mocked(savePantrySentence).mockReset();
  });

  it("previews a sentence and adds those items", async () => {
    const user = userEvent.setup();
    const onAdded = vi.fn();
    vi.mocked(previewPantrySentence).mockResolvedValue(preview);
    vi.mocked(savePantrySentence).mockResolvedValue([
      savedLeeks,
      { ...savedLeeks, id: "chicken", name: "Chicken", quantity: "500", unit: "g", dimension: "mass" },
    ]);

    render(<SentenceAdd onAdded={onAdded} />);
    await user.type(screen.getByLabelText("Sentence"), "2 leeks and 500 g chicken");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByRole("list", { name: "Preview" })).toBeInTheDocument();
    expect(screen.getByText("Leeks")).toBeInTheDocument();
    expect(screen.getByText("2 count · new")).toBeInTheDocument();
    expect(screen.getByText("Chicken")).toBeInTheDocument();
    expect(screen.getByText("500 g · new")).toBeInTheDocument();
    expect(previewPantrySentence).toHaveBeenCalledWith("2 leeks and 500 g chicken");

    await user.click(screen.getByRole("button", { name: "Add these" }));
    expect(savePantrySentence).toHaveBeenCalledWith([
      { name: "Leeks", quantity: "2", unit: "count" },
      { name: "Chicken", quantity: "500", unit: "g" },
    ]);
    expect(onAdded).toHaveBeenCalled();
    expect(screen.queryByRole("list", { name: "Preview" })).not.toBeInTheDocument();
  });

  it("shows a bad sentence and does not save", async () => {
    const user = userEvent.setup();
    vi.mocked(previewPantrySentence).mockRejectedValue(
      new ApiError({
        type: "https://pantrycook.dev/problems/sentence_unparsed",
        title: "Sentence Unparsed",
        status: 422,
        detail: 'Couldn\'t read "hello". Name a quantity, like "500 g chicken".',
        instance: "/api/items/sentence/preview",
        code: "sentence_unparsed",
        request_id: "req-1",
      }),
    );

    render(<SentenceAdd onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Sentence"), "hello");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't read \"hello\"");
    expect(screen.queryByRole("button", { name: "Add these" })).not.toBeInTheDocument();
    expect(savePantrySentence).not.toHaveBeenCalled();
  });
});
