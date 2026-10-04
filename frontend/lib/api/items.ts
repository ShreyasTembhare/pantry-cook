import { z } from "zod";

import {
  amountSchema,
  dimensionSchema,
  request,
  unitSchema,
  type Unit,
} from "@/lib/api/client";

export const itemSchema = z.object({
  id: z.string(),
  name: z.string(),
  quantity: z.union([z.string(), z.number()]).transform((value) => {
    const numeric = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(numeric)) return String(value);
    return String(numeric);
  }),
  unit: unitSchema,
  dimension: dimensionSchema,
  expires_on: z.string().nullable(),
  version: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type Item = z.infer<typeof itemSchema>;

export type ItemInput = {
  name: string;
  quantity: string;
  unit: Unit;
  expires_on: string | null;
};

export type ItemPatch = Partial<ItemInput> & {
  version: number;
};

export function listItems(): Promise<Item[]> {
  return request("/api/items?sort=expires_on", z.array(itemSchema));
}

export function createItem(input: ItemInput): Promise<Item> {
  return request("/api/items", itemSchema, {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      quantity: input.quantity,
      unit: input.unit,
      expires_on: input.expires_on,
    }),
  });
}

export function updateItem(id: string, input: ItemPatch): Promise<Item> {
  return request(`/api/items/${id}`, itemSchema, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteItem(id: string): Promise<void> {
  return request(`/api/items/${id}`, z.undefined(), { method: "DELETE" });
}

export const sentencePreviewLineSchema = z.object({
  name: z.string(),
  quantity: amountSchema,
  unit: unitSchema,
  action: z.enum(["create", "add"]),
});

export const sentencePreviewSchema = z.object({
  sentence: z.string(),
  items: z.array(sentencePreviewLineSchema).min(1),
});

export type SentencePreviewLine = z.infer<typeof sentencePreviewLineSchema>;
export type SentencePreview = z.infer<typeof sentencePreviewSchema>;

export function previewPantrySentence(sentence: string): Promise<SentencePreview> {
  return request("/api/items/sentence/preview", sentencePreviewSchema, {
    method: "POST",
    body: JSON.stringify({ sentence }),
  });
}

export function savePantrySentence(
  items: { name: string; quantity: string; unit: Unit }[],
): Promise<Item[]> {
  return request("/api/items/sentence", z.array(itemSchema), {
    method: "POST",
    body: JSON.stringify({
      items: items.map((item) => ({
        name: item.name,
        quantity: item.quantity,
        unit: item.unit,
      })),
    }),
  });
}

export function mergeItem(id: string, input: { quantity: string; unit: Unit }): Promise<Item> {
  return request(`/api/items/${encodeURIComponent(id)}/merge`, itemSchema, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
