"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatMessage } from "@/components/chat/chat-message";
import { Pip } from "@/components/mascot/pip";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  cancelChatPending,
  confirmChatPending,
  getChat,
  listItems,
  type ChatCard,
  type ChatMessage as ChatMessageModel,
  type ChatThread,
  type ChatTurn,
} from "@/lib/api";
import { suggestionChips } from "@/lib/cook";
import { localISODate } from "@/lib/pantry";
import { useChatTurn } from "@/lib/use-chat-turn";

function cookSessionFromCards(cards: ChatCard[]): string | null {
  for (const card of cards) {
    if (card.cook_session_id) return card.cook_session_id;
  }
  return null;
}

export function ChatHome() {
  const client = useQueryClient();
  const threadQuery = useQuery({ queryKey: ["chat"], queryFn: getChat, retry: 1 });
  const itemsQuery = useQuery({ queryKey: ["items"], queryFn: listItems });
  const { thinking, send } = useChatTurn();
  const [pendingUser, setPendingUser] = useState<ChatMessageModel | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const today = localISODate(new Date());

  const messages = threadQuery.data?.messages ?? [];
  const visible = pendingUser ? [...messages, pendingUser] : messages;
  const chips = suggestionChips(itemsQuery.data ?? [], today).map((chip) => chip.sentence);

  const confirm = useMutation({
    mutationFn: ({ id, acknowledge }: { id: string; acknowledge: boolean }) =>
      confirmChatPending(id, acknowledge),
    onSuccess: async (message) => {
      appendAssistantMessage(message);
      await client.invalidateQueries({ queryKey: ["items"] });
      await client.invalidateQueries({ queryKey: ["meals"] });
      await client.invalidateQueries({ queryKey: ["cook-sessions"] });
      await client.invalidateQueries({ queryKey: ["chat"] });
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "Couldn't confirm that.");
    },
  });

  const cancel = useMutation({
    mutationFn: cancelChatPending,
    onSuccess: (message) => {
      appendAssistantMessage(message);
      void client.invalidateQueries({ queryKey: ["chat"] });
    },
  });

  function appendAssistantMessage(message: ChatMessageModel) {
    client.setQueryData<ChatThread>(["chat"], (old) => {
      if (!old) {
        return {
          id: "local-thread",
          active_cook_session_id: null,
          messages: [message],
        };
      }
      if (old.messages.some((row) => row.id === message.id)) return old;
      return { ...old, messages: [...old.messages, message] };
    });
  }

  function mergeTurn(turn: ChatTurn) {
    const cookSession = cookSessionFromCards(turn.assistant.cards);
    client.setQueryData<ChatThread>(["chat"], (old) => {
      const base: ChatThread = old ?? {
        id: turn.thread_id,
        active_cook_session_id: null,
        messages: [],
      };
      const seen = new Set(base.messages.map((message) => message.id));
      const nextMessages = [...base.messages];
      if (!seen.has(turn.user.id)) nextMessages.push(turn.user);
      if (!seen.has(turn.assistant.id)) nextMessages.push(turn.assistant);
      return {
        ...base,
        id: turn.thread_id,
        active_cook_session_id: cookSession ?? base.active_cook_session_id,
        messages: nextMessages,
      };
    });
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [visible.length, thinking, threadQuery.dataUpdatedAt]);

  async function say(text: string) {
    const trimmed = text.trim();
    if (!trimmed || thinking || confirm.isPending || cancel.isPending) return;
    setPendingUser({
      id: `pending-user-${Date.now()}`,
      role: "user",
      content: trimmed,
      cards: [],
      created_at: new Date().toISOString(),
    });
    try {
      const turn = await send(trimmed);
      mergeTurn(turn);
      setPendingUser(null);
    } catch (error) {
      setPendingUser(null);
      toast.error(error instanceof ApiError ? error.message : "Pip couldn't reply. Try again.");
    }
  }

  const busy = thinking || confirm.isPending || cancel.isPending;
  const showWelcome =
    visible.length === 0 && !thinking && !threadQuery.isPending && !threadQuery.isError;

  return (
    <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6">
          {threadQuery.isError ? (
            <div className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
              <p>Couldn&apos;t load your conversation.</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => void threadQuery.refetch()}
              >
                Retry
              </Button>
            </div>
          ) : null}
          {threadQuery.isPending && messages.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
              Loading chat…
            </div>
          ) : null}
          {showWelcome ? (
            <div className="flex flex-col items-center px-4 pb-8 pt-2 text-center">
              <Pip className="h-20 w-16" />
              <h2 className="mt-4 font-serif text-3xl tracking-tight">What should we cook?</h2>
              <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
                Tell Pip what&apos;s in the kitchen, ask for a meal, or change a recipe until it
                fits tonight.
              </p>
            </div>
          ) : null}
          {visible.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              pantry={itemsQuery.data ?? []}
              busy={busy}
              onConfirmPending={(id, acknowledge) => confirm.mutate({ id, acknowledge })}
              onCancelPending={(id) => cancel.mutate(id)}
              onRevise={(note) => void say(`Revise the meal: ${note}`)}
              onAbandon={() => void say("abandon this meal")}
              onAskConfirm={() => void say("looks good")}
            />
          ))}
          {thinking ? (
            <div className="flex items-center gap-3" aria-live="polite">
              <Pip mood="thinking" className="h-10 w-9" />
              <p className="text-sm text-muted-foreground">Pip is thinking…</p>
            </div>
          ) : null}
          <div ref={bottomRef} aria-hidden />
        </div>
      </div>
      <ChatComposer busy={busy} suggestions={chips} onSend={(text) => void say(text)} />
    </div>
  );
}
