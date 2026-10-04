import { z } from "zod";

import { trimAmount } from "@/lib/quantity";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8787").replace(
  /\/$/,
  "",
);

export const unitSchema = z.enum(["g", "kg", "ml", "L", "count"]);
export const dimensionSchema = z.enum(["mass", "volume", "count"]);

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

export async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
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

export const amountSchema = z.union([z.string(), z.number()]).transform((value) => {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return trimAmount(numeric);
});

export const nullableAmountSchema = z
  .union([z.string(), z.number(), z.null()])
  .optional()
  .transform((value) => {
    if (value == null) return null;
    const numeric = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(numeric)) return null;
    return trimAmount(numeric);
  });

const healthSchema = z.object({
  status: z.string(),
  db: z.string(),
  checkpointer: z.string().optional(),
  llm: z.string(),
  pending_sessions: z.number().int().optional(),
});

export type Health = z.infer<typeof healthSchema>;

export function getHealth(): Promise<Health> {
  return request("/api/health", healthSchema);
}
