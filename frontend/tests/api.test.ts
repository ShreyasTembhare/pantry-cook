import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createItem,
  deleteItem,
  listItems,
  previewPantrySentence,
  problemDetailsSchema,
  savePantrySentence,
} from "@/lib/api";

const problem = {
  type: "https://pantrycook.dev/problems/duplicate_item",
  title: "Duplicate Item",
  status: 409,
  detail: "An item named 'Rice' already exists",
  instance: "/api/items",
  code: "duplicate_item",
  extra: { existing_id: "abc" },
  request_id: "req-1",
};

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("items API client", () => {
  it("parses a pantry list and normalises decimal quantities", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        {
          id: "1",
          name: "Flour",
          quantity: "1.50",
          unit: "kg",
          dimension: "mass",
          expires_on: null,
          version: 1,
          created_at: "2026-09-01T00:00:00",
          updated_at: "2026-09-01T00:00:00",
        },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const items = await listItems();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8787/api/items?sort=expires_on",
      expect.objectContaining({ headers: expect.objectContaining({ Accept: "application/json" }) }),
    );
    expect(items[0]?.quantity).toBe("1.5");
    expect(items[0]?.unit).toBe("kg");
  });

  it("posts a new item", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          id: "2",
          name: "Rice",
          quantity: "500.00",
          unit: "g",
          dimension: "mass",
          expires_on: null,
          version: 1,
          created_at: "2026-09-01T00:00:00",
          updated_at: "2026-09-01T00:00:00",
        },
        201,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const item = await createItem({
      name: "Rice",
      quantity: "500",
      unit: "g",
      expires_on: null,
    });

    expect(item.name).toBe("Rice");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      name: "Rice",
      quantity: "500",
      unit: "g",
      expires_on: null,
    });
  });

  it("turns problem details into an ApiError", async () => {
    expect(problemDetailsSchema.parse(problem).code).toBe("duplicate_item");

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(problem, 409)));

    const error = await createItem({
      name: "Rice",
      quantity: "200",
      unit: "g",
      expires_on: null,
    }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).problem.code).toBe("duplicate_item");
    expect((error as ApiError).problem.detail).toBe("An item named 'Rice' already exists");
    expect((error as ApiError).message).toBe("An item named 'Rice' already exists");
  });

  it("treats an unreadable error body as an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>", { status: 500 })),
    );

    await expect(listItems()).rejects.toMatchObject({
      name: "ApiError",
      problem: expect.objectContaining({ code: "invalid_response", status: 500 }),
    });
  });

  it("previews a sentence and saves the batch", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          sentence: "2 leeks and 500 g chicken",
          items: [
            { name: "Leeks", quantity: "2", unit: "count", action: "create" },
            { name: "Chicken", quantity: "500.00", unit: "g", action: "create" },
          ],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            id: "leeks",
            name: "Leeks",
            quantity: "2",
            unit: "count",
            dimension: "count",
            expires_on: null,
            version: 1,
            created_at: "2026-09-01T00:00:00",
            updated_at: "2026-09-01T00:00:00",
          },
        ]),
      );
    vi.stubGlobal("fetch", fetchMock);

    const preview = await previewPantrySentence("2 leeks and 500 g chicken");
    expect(preview.items[1]?.quantity).toBe("500");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8787/api/items/sentence/preview");

    const saved = await savePantrySentence(preview.items);
    expect(saved[0]?.name).toBe("Leeks");
    const saveCall = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(saveCall[0]).toBe("http://127.0.0.1:8787/api/items/sentence");
    expect(JSON.parse(String(saveCall[1].body))).toEqual({
      items: [
        { name: "Leeks", quantity: "2", unit: "count" },
        { name: "Chicken", quantity: "500", unit: "g" },
      ],
    });
  });

  it("surfaces a bad sentence as an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            ...problem,
            status: 422,
            code: "sentence_unparsed",
            detail: 'Couldn\'t read that as pantry items. Try "2 leeks and 500 g chicken".',
            instance: "/api/items/sentence/preview",
          },
          422,
        ),
      ),
    );

    await expect(previewPantrySentence("hello")).rejects.toMatchObject({
      name: "ApiError",
      problem: expect.objectContaining({ code: "sentence_unparsed" }),
    });
  });

  it("accepts a 204 delete", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteItem("item-1")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8787/api/items/item-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
