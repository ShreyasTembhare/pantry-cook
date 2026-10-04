import { z } from "zod";

import { amountSchema, API_URL, request, unitSchema } from "@/lib/api/client";
import { mealSchema, type Meal } from "@/lib/api/meals";

const useLineSchema = z.object({
  kind: z.literal("use"),
  item_id: z.string(),
  quantity: amountSchema,
  unit: unitSchema,
});

const missingLineSchema = z.object({
  kind: z.literal("missing"),
  name: z.string(),
  quantity_note: z.string().nullable().optional(),
});

export const proposalSchema = z.object({
  title: z.string(),
  servings: z.number().int(),
  lines: z.array(z.discriminatedUnion("kind", [useLineSchema, missingLineSchema])),
  steps: z.array(z.string()),
  rationale: z.string().nullable().optional(),
});

const violationSchema = z.object({
  code: z.string(),
  message: z.string(),
  item_id: z.string().nullable().optional(),
  detail: z.record(z.string(), z.unknown()).optional(),
});

const cookErrorSchema = z
  .object({
    code: z.string().optional(),
    detail: z.string().optional(),
    retry_after: z.number().optional(),
  })
  .passthrough();

export const proposalAttemptSchema = z.object({
  attempt_no: z.number().int(),
  trigger: z.enum(["initial", "auto_repair", "user_revision"]),
  user_note: z.string().nullable(),
  proposal: proposalSchema.nullable(),
});

export const cookSessionSchema = z.object({
  id: z.string(),
  status: z.enum(["running", "awaiting_user", "committed", "abandoned", "failed"]),
  sentence: z.string(),
  attempt_count: z.number().int(),
  proposal: proposalSchema.nullable(),
  proposal_etag: z.string().nullable(),
  violations: z.array(violationSchema).optional().transform((value) => value ?? []),
  attempts: z
    .array(proposalAttemptSchema)
    .optional()
    .transform((value) => value ?? []),
  meal_id: z.string().nullable(),
  error: cookErrorSchema.nullable(),
  stale: z.boolean().optional().transform((value) => Boolean(value)),
  created_at: z.string(),
  updated_at: z.string(),
  expires_at: z.string(),
});

export const cookSummarySchema = z.object({
  id: z.string(),
  status: cookSessionSchema.shape.status,
  sentence: z.string(),
  attempt_count: z.number().int(),
  updated_at: z.string(),
});

export type Proposal = z.infer<typeof proposalSchema>;
export type CookSession = z.infer<typeof cookSessionSchema>;
export type CookSummary = z.infer<typeof cookSummarySchema>;

export function cookStreamUrl(id: string): string {
  return `${API_URL}/api/cook/${encodeURIComponent(id)}/stream`;
}

export function startCook(sentence: string, options?: { defer?: boolean }): Promise<CookSession> {
  return request("/api/cook/start", cookSessionSchema, {
    method: "POST",
    body: JSON.stringify({ sentence, defer: Boolean(options?.defer) }),
  });
}

export function listCookSessions(status = "awaiting_user"): Promise<CookSummary[]> {
  return request(`/api/cook?status=${encodeURIComponent(status)}`, z.array(cookSummarySchema));
}

export function getCook(id: string): Promise<CookSession> {
  return request(`/api/cook/${id}`, cookSessionSchema);
}

export function reviseCook(
  id: string,
  note: string,
  options?: { defer?: boolean },
): Promise<CookSession> {
  return request(`/api/cook/${id}/revise`, cookSessionSchema, {
    method: "POST",
    body: JSON.stringify({ note, defer: Boolean(options?.defer) }),
  });
}

export function confirmCook(
  id: string,
  proposalEtag: string,
  options?: { acknowledgeExpired?: boolean },
): Promise<Meal> {
  return request(`/api/cook/${id}/confirm`, mealSchema, {
    method: "POST",
    body: JSON.stringify({
      proposal_etag: proposalEtag,
      acknowledge_expired: Boolean(options?.acknowledgeExpired),
    }),
  });
}

export function abandonCook(id: string): Promise<CookSession> {
  return request(`/api/cook/${id}/abandon`, cookSessionSchema, { method: "POST" });
}
