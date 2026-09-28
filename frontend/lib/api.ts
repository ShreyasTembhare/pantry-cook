import { z } from "zod";

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
