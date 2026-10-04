import { z } from "zod";

import { trimAmount } from "@/lib/quantity";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8787").replace(/\/$/, "");

export const unitSchema = z.enum(["g", "kg", "ml", "L", "count"]);
export const dimensionSchema = z.enum(["mass", "volume", "count"]);

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

export const fieldErrorSchema = z.object({
  loc: z.array(z.union([z.string(), z.number()])),
  msg: z.string(),
  type: z.string(),
});

export const problemDetailsSchema = z.object({
  type: z.string(),
  title: z.string(),
  status: z.number().int(),
  detail: z.string(),
  instance: z.string(),
  code: z.string(),
  errors: z.array(fieldErrorSchema).nullable().optional(),
  extra: z.record(z.string(), z.unknown()).nullable().optional(),
  request_id: z.string(),
});

export type Unit = z.infer<typeof unitSchema>;
export type Item = z.infer<typeof itemSchema>;
export type ProblemDetails = z.infer<typeof problemDetailsSchema>;
export type FieldError = z.infer<typeof fieldErrorSchema>;

export class ApiError extends Error {
  readonly problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super(problem.detail);
    this.name = "ApiError";
    this.problem = problem;
  }
}

export type ItemInput = {
  name: string;
  quantity: string;
  unit: Unit;
  expires_on: string | null;
};

export type ItemPatch = Partial<ItemInput> & {
  version: number;
};

function problemFromUnknown(status: number, path: string, requestId: string): ProblemDetails {
  return {
    type: "about:blank",
    title: status === 0 ? "Network error" : "Request failed",
    status,
    detail:
      status === 0
        ? "Couldn't reach the pantry. Check that the kitchen server is running."
        : "The pantry returned something we couldn't read.",
    instance: path,
    code: status === 0 ? "network" : "invalid_response",
    request_id: requestId,
  };
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(problemFromUnknown(0, path, ""));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const json = await parseBody(response);
  const requestId = response.headers.get("x-request-id") ?? "";

  if (!response.ok) {
    const problem = problemDetailsSchema.safeParse(json);
    if (problem.success) throw new ApiError(problem.data);
    throw new ApiError(problemFromUnknown(response.status, path, requestId));
  }

  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    throw new ApiError(problemFromUnknown(response.status, path, requestId));
  }
  return parsed.data;
}

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

const amountSchema = z.union([z.string(), z.number()]).transform((value) => {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return trimAmount(numeric);
});

const nullableAmountSchema = z
  .union([z.string(), z.number(), z.null()])
  .optional()
  .transform((value) => {
    if (value == null) return null;
    const numeric = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(numeric)) return null;
    return trimAmount(numeric);
  });

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

export const mealListItemSchema = mealSchema.omit({ steps: true, lines: true, cook_session_id: true });

const healthSchema = z.object({
  status: z.string(),
  db: z.string(),
  checkpointer: z.string().optional(),
  llm: z.string(),
  pending_sessions: z.number().int().optional(),
});

export type CookSession = z.infer<typeof cookSessionSchema>;
export type CookSummary = z.infer<typeof cookSummarySchema>;
export type Meal = z.infer<typeof mealSchema>;
export type MealListItem = z.infer<typeof mealListItemSchema>;
export type MealLine = z.infer<typeof mealLineSchema>;
export type MealStatus = "cooked" | "proposed" | "undone";
export type Health = z.infer<typeof healthSchema>;

export function getHealth(): Promise<Health> {
  return request("/api/health", healthSchema);
}

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

export function mergeItem(
  id: string,
  input: { quantity: string; unit: Unit },
): Promise<Item> {
  return request(`/api/items/${encodeURIComponent(id)}/merge`, itemSchema, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function abandonCook(id: string): Promise<CookSession> {
  return request(`/api/cook/${id}/abandon`, cookSessionSchema, { method: "POST" });
}

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

export function fieldErrorsFromProblem(problem: ProblemDetails): Partial<Record<string, string>> {
  const errors: Partial<Record<string, string>> = {};
  for (const error of problem.errors ?? []) {
    const field = error.loc.filter((part) => part !== "body").at(-1);
    if (typeof field === "string") {
      errors[field] = error.msg.replace(/^Value error,\s*/, "");
    }
  }
  return errors;
}

export const chatCardSchema = z.object({
  type: z.enum(["pantry", "pending", "proposal", "meals", "meal", "error", "note"]),
  title: z.string(),
  pending_id: z.string().nullable().optional(),
  pending_kind: z.enum(["delete_item", "confirm_cook", "undo_meal"]).nullable().optional(),
  items: z.array(itemSchema).optional().default([]),
  proposal: z.record(z.string(), z.unknown()).nullable().optional(),
  cook_session_id: z.string().nullable().optional(),
  proposal_etag: z.string().nullable().optional(),
  meals: z.array(z.record(z.string(), z.unknown())).optional().default([]),
  meal: z.record(z.string(), z.unknown()).nullable().optional(),
  error: z.record(z.string(), z.unknown()).nullable().optional(),
});

export const chatMessageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant", "system"]),
  content: z.string(),
  cards: z.array(chatCardSchema).default([]),
  created_at: z.string(),
});

export const chatThreadSchema = z.object({
  id: z.string(),
  active_cook_session_id: z.string().nullable(),
  messages: z.array(chatMessageSchema),
});

export const chatTurnSchema = z.object({
  thread_id: z.string(),
  user: chatMessageSchema,
  assistant: chatMessageSchema,
});

export type ChatCard = z.infer<typeof chatCardSchema>;
export type ChatMessage = z.infer<typeof chatMessageSchema>;
export type ChatThread = z.infer<typeof chatThreadSchema>;
export type ChatTurn = z.infer<typeof chatTurnSchema>;

export function getChat(): Promise<ChatThread> {
  return request("/api/chat", chatThreadSchema);
}

export function sendChatMessage(text: string): Promise<ChatTurn> {
  return request("/api/chat/messages", chatTurnSchema, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function confirmChatPending(
  pendingId: string,
  acknowledgeExpired = false,
): Promise<ChatMessage> {
  const query = acknowledgeExpired ? "?acknowledge_expired=true" : "";
  return request(`/api/chat/pending/${pendingId}/confirm${query}`, chatMessageSchema, {
    method: "POST",
  });
}

export function cancelChatPending(pendingId: string): Promise<ChatMessage> {
  return request(`/api/chat/pending/${pendingId}/cancel`, chatMessageSchema, {
    method: "POST",
  });
}
