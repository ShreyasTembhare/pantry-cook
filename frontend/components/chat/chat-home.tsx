"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ChatComposer, type PantryState } from "@/components/chat/chat-composer";
import { ChatMessage } from "@/components/chat/chat-message";
import { ChatStatus } from "@/components/chat/chat-status";
import { Pip } from "@/components/mascot/pip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { ScrollArea } from "@/components/ui/scroll-area";
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
import { liveCookCardKey, openPendingCard, sendFailure } from "@/lib/chat";
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
  const [failed, setFailed] = useState<{ text: string; message: string; action: string } | null>(
    null,
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const today = localISODate(new Date());

  const messages = threadQuery.data?.messages ?? [];
  const failedMessage: ChatMessageModel | null = failed
    ? {
        id: "failed-user-1",
        role: "user",
        content: failed.text,
        cards: [],
        created_at: new Date().toISOString(),
      }
    : null;
  const visible = [
    ...messages,
    ...(pendingUser ? [pendingUser] : []),
    ...(failedMessage ? [failedMessage] : []),
  ];
  const chips = suggestionChips(itemsQuery.data ?? [], today).map((chip) => chip.sentence);
  const openPending = openPendingCard(messages);
  const liveCook = liveCookCardKey(messages, threadQuery.data?.active_cook_session_id ?? null);
  const pantryState: PantryState = itemsQuery.isError
    ? "error"
    : itemsQuery.isPending
      ? "loading"
      : (itemsQuery.data ?? []).length === 0
        ? "empty"
        : "ready";

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
    if (visible.length === 0 && !thinking) return;
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [visible.length, thinking, threadQuery.dataUpdatedAt]);

  async function say(text: string) {
    const trimmed = text.trim();
    if (!trimmed || thinking || confirm.isPending || cancel.isPending) return;
    setFailed(null);
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
      void client.invalidateQueries({ queryKey: ["chat"] });
    } catch (error) {
      setPendingUser(null);
      const shown = sendFailure(error);
      setFailed({ text: trimmed, ...shown });
      toast.error(shown.message);
    }
  }

  const busy = thinking || confirm.isPending || cancel.isPending;
  const showWelcome =
    visible.length === 0 && !thinking && !threadQuery.isPending && !threadQuery.isError;

  return (
    <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col">
      <ChatStatus
        cookSessionId={threadQuery.data?.active_cook_session_id ?? null}
        pending={openPending}
      />
      <ScrollArea className="min-h-0 flex-1 overflow-hidden">
        <div
          role="log"
          aria-label="Conversation"
          aria-live="polite"
          className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6"
        >
          {threadQuery.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Couldn&apos;t load your conversation.</AlertTitle>
              <AlertDescription>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void threadQuery.refetch()}
                >
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
          {threadQuery.isPending && messages.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
              Loading chat…
            </div>
          ) : null}
          {showWelcome ? (
            <Empty className="border-0 bg-transparent px-4 py-4">
              <EmptyHeader>
                <EmptyMedia>
                  <Pip className="h-20 w-16" />
                </EmptyMedia>
                <EmptyTitle className="font-serif text-3xl font-normal tracking-tight">
                  What should we cook?
                </EmptyTitle>
                <EmptyDescription>
                  Tell Pip what&apos;s in the kitchen, ask for a meal, or change a recipe until it
                  fits tonight.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}
          {visible.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              pantry={itemsQuery.data ?? []}
              busy={busy}
              openPendingId={openPending?.pending_id ?? null}
              liveCookCardKey={liveCook}
              onConfirmPending={(id, acknowledge) => confirm.mutate({ id, acknowledge })}
              onCancelPending={(id) => cancel.mutate(id)}
              onRevise={(note) => void say(`Revise the meal: ${note}`)}
              onAbandon={() => void say("abandon this meal")}
              onAskConfirm={() => void say("looks good")}
            />
          ))}
          {failed ? (
            <Alert variant="destructive">
              <AlertTitle>Message didn&apos;t send</AlertTitle>
              <AlertDescription className="flex flex-wrap items-center gap-2">
                <span>{failed.message}</span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void say(failed.text)}
                >
                  {failed.action}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setFailed(null)}
                >
                  Dismiss
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
          {thinking ? (
            <div className="flex items-center gap-3">
              <Pip mood="thinking" className="h-10 w-9" />
              <p className="text-sm text-muted-foreground">Pip is thinking…</p>
            </div>
          ) : null}
          <div ref={bottomRef} aria-hidden />
        </div>
      </ScrollArea>
      <ChatComposer
        busy={busy}
        suggestions={chips}
        pantryState={pantryState}
        onRetryPantry={() => void itemsQuery.refetch()}
        onSend={(text) => void say(text)}
      />
    </div>
  );
}
