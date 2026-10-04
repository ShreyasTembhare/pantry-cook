import { z } from "zod";

import { request } from "@/lib/api/client";
import { proposalSchema } from "@/lib/api/cook";
import { itemSchema } from "@/lib/api/items";
import { mealListItemSchema, mealSchema } from "@/lib/api/meals";

const chatErrorSchema = z
  .object({
    code: z.string(),
    detail: z.string(),
  })
  .passthrough();

export const chatCardSchema = z.object({
  type: z.enum(["pantry", "pending", "proposal", "meals", "meal", "error", "note"]),
  title: z.string(),
  pending_id: z.string().nullable().optional(),
  pending_kind: z.enum(["delete_item", "confirm_cook", "undo_meal"]).nullable().optional(),
  items: z.array(itemSchema).optional().default([]),
  proposal: proposalSchema.nullable().optional(),
  cook_session_id: z.string().nullable().optional(),
  proposal_etag: z.string().nullable().optional(),
  meals: z.array(mealListItemSchema).optional().default([]),
  meal: mealSchema.nullable().optional(),
  error: chatErrorSchema.nullable().optional(),
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
