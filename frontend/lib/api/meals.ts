import { z } from "zod";

import { amountSchema, nullableAmountSchema, request, unitSchema, type Unit } from "@/lib/api/client";

const mealLineSchema = z.object({
  id: z.string(),
  kind: z.string(),
  item_id: z.string().nullable(),
  item_name: z.string(),
  quantity: nullableAmountSchema,
  unit: unitSchema.nullable().optional().transform((value) => value ?? null),
  missing_name: z.string().nullable().optional(),
  missing_note: z.string().nullable().optional(),
  position: z.number().int(),
});

export const mealSchema = z.object({
  id: z.string(),
  title: z.string(),
  sentence: z.string(),
  servings: z.number().int(),
  status: z.string(),
  cooked_at: z.string().nullable(),
  created_at: z.string(),
  use_count: z.number().int(),
  missing_count: z.number().int(),
  steps: z.array(z.string()).optional().transform((value) => value ?? []),
  lines: z.array(mealLineSchema).optional().transform((value) => value ?? []),
  cook_session_id: z.string().nullable().optional(),
});

export const mealListItemSchema = mealSchema.omit({
  steps: true,
  lines: true,
  cook_session_id: true,
});

export type Meal = z.infer<typeof mealSchema>;
export type MealListItem = z.infer<typeof mealListItemSchema>;
export type MealLine = z.infer<typeof mealLineSchema>;
export type MealStatus = "cooked" | "proposed" | "undone";

export function listMeals(status: MealStatus = "cooked"): Promise<MealListItem[]> {
  return request(`/api/meals?status=${encodeURIComponent(status)}`, z.array(mealListItemSchema));
}

export function getMeal(id: string): Promise<Meal> {
  return request(`/api/meals/${id}`, mealSchema);
}

export function undoMeal(id: string): Promise<Meal> {
  return request(`/api/meals/${id}/undo`, mealSchema, { method: "POST" });
}

export const boughtLineSchema = z.object({
  meal: mealSchema,
  item_id: z.string(),
  item_name: z.string(),
  quantity: amountSchema,
  unit: unitSchema,
  created: z.boolean(),
});

export type BoughtLine = z.infer<typeof boughtLineSchema>;

export function buyMissingLine(
  mealId: string,
  lineId: string,
  input?: { quantity: string; unit: Unit },
): Promise<BoughtLine> {
  return request(
    `/api/meals/${encodeURIComponent(mealId)}/lines/${encodeURIComponent(lineId)}/bought`,
    boughtLineSchema,
    {
      method: "POST",
      body: JSON.stringify(input ?? {}),
    },
  );
}
