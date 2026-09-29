"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { CookErrorCard } from "@/components/cook/cook-error";
import { ProposalSkeleton } from "@/components/cook/cook-skeleton";
import { ProgressRail } from "@/components/cook/progress-rail";
import { ProposalCard, type PantryAmount, type ProposalView } from "@/components/cook/proposal-card";
import { Button } from "@/components/ui/button";
import {
  abandonCook,
  ApiError,
  confirmCook,
  getCook,
  listItems,
  reviseCook,
  startCook,
  type CookSession,
} from "@/lib/api";
import { cookErrorPresentation, retriesSameSentence } from "@/lib/cook";
import { proposalFromTokens } from "@/lib/reveal";
import { useCookStream } from "@/lib/use-cook-stream";
import { useRevealedProposal } from "@/lib/use-revealed-proposal";

const REPROPOSE_NOTE = "The pantry changed. Propose again from what's there now.";

function retrySeconds(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}

export function CookSessionView({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [staleOverride, setStaleOverride] = useState<string | null>(null);
  const [actionError, setActionError] = useState<ApiError | null>(null);

  const sessionQuery = useQuery({
    queryKey: ["cook", id],
    queryFn: () => getCook(id),
  });

  const itemsQuery = useQuery({
    queryKey: ["items"],
    queryFn: listItems,
  });

  function remember(session: CookSession) {
    queryClient.setQueryData(["cook", id], session);
    void queryClient.invalidateQueries({ queryKey: ["cook-sessions"] });
  }

  const revise = useMutation({
    mutationFn: (note: string) => reviseCook(id, note, { defer: true }),
    onSuccess: (session) => {
      setStaleOverride(null);
      setActionError(null);
      remember(session);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setActionError(error);
        return;
      }
      toast.error("Couldn't revise that proposal.");
    },
  });

  const confirm = useMutation({
    mutationFn: (input: { etag: string; acknowledgeExpired: boolean }) =>
      confirmCook(id, input.etag, { acknowledgeExpired: input.acknowledgeExpired }),
    onSuccess: (meal) => {
      void queryClient.invalidateQueries({ queryKey: ["items"] });
      void queryClient.invalidateQueries({ queryKey: ["meals"] });
      void queryClient.invalidateQueries({ queryKey: ["cook-sessions"] });
      toast.success("Cooked. Pantry updated.", {
        action: {
          label: "View meal",
          onClick: () => router.push(`/meals/${meal.id}`),
        },
      });
      router.push(`/meals/${meal.id}`);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.problem.code === "expired_unacknowledged") {
        toast.error(error.problem.detail);
        return;
      }
      if (error instanceof ApiError && error.problem.code === "stale_proposal") {
        const reason = error.problem.extra?.reason;
        setStaleOverride(
          reason === "proposal_etag_mismatch"
            ? "This proposal is out of date. Re-propose before confirming."
            : "Your pantry changed since this was proposed.",
        );
        void queryClient.invalidateQueries({ queryKey: ["cook", id] });
        void queryClient.invalidateQueries({ queryKey: ["items"] });
        return;
      }
      if (error instanceof ApiError) {
        setActionError(error);
        return;
      }
      toast.error("Couldn't confirm that meal.");
    },
  });

  const abandon = useMutation({
    mutationFn: () => abandonCook(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cook-sessions"] });
      toast("Proposal abandoned.");
      router.push("/cook");
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.problem.detail : "Couldn't abandon that.");
    },
  });

  const restart = useMutation({
    mutationFn: (sentence: string) => startCook(sentence, { defer: true }),
    onSuccess: (session) => {
      queryClient.setQueryData(["cook", session.id], session);
      void queryClient.invalidateQueries({ queryKey: ["cook-sessions"] });
      router.replace(`/cook/${session.id}`);
    },
    onError: (error) => {
      if (error instanceof ApiError) setActionError(error);
      else toast.error("Couldn't start again.");
    },
  });

  const busy = revise.isPending || confirm.isPending || abandon.isPending || restart.isPending;
  const session = sessionQuery.data;
  const streaming = session?.status === "running";
  const stream = useCookStream(id, streaming, remember);
  const partial = useMemo(
    () => (streaming ? proposalFromTokens(stream.tokens) : null),
    [streaming, stream.tokens],
  );
  const fullProposal: ProposalView | null =
    stream.proposal ?? (session?.status === "awaiting_user" ? (session.proposal ?? null) : null);
  const revealed = useRevealedProposal(fullProposal, Boolean(stream.proposal));

  function recoverFrom(error: ApiError, sentence?: string) {
    const presentation = cookErrorPresentation(error.problem.code, error.problem.detail);
    if (presentation.action === "Add items") {
      router.push("/");
      return;
    }
    if (presentation.action === "Re-propose") {
      revise.mutate(REPROPOSE_NOTE);
      return;
    }
    if (retriesSameSentence(presentation.action) && sentence) {
      restart.mutate(sentence);
      return;
    }
    const params = sentence ? `?sentence=${encodeURIComponent(sentence)}` : "";
    router.push(`/cook${params}`);
  }

  if (sessionQuery.isPending) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        <ProposalSkeleton />
      </div>
    );
  }

  if (sessionQuery.isError || !session) {
    const problem = sessionQuery.error instanceof ApiError ? sessionQuery.error.problem : null;
    const missing = problem?.code === "session_not_found";
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">Cook</h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
          {missing
            ? "That cook session isn't here. It may have been started on another pantry."
            : problem?.detail || "Couldn't load this proposal."}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {missing ? null : (
            <Button
              type="button"
              variant="outline"
              className="h-11 lg:h-9"
              onClick={() => void sessionQuery.refetch()}
            >
              Retry
            </Button>
          )}
          <Button asChild variant="ghost" className="h-11 lg:h-9">
            <Link href="/cook">Back to cook</Link>
          </Button>
        </div>
      </div>
    );
  }

  const pantry: Record<string, PantryAmount> = {};
  for (const item of itemsQuery.data ?? []) {
    pantry[item.id] = {
      name: item.name,
      quantity: item.quantity,
      unit: item.unit,
      expires_on: item.expires_on,
    };
  }

  const stale = Boolean(staleOverride) || session.stale;
  const failed = session.status === "failed";
  const errorCode = typeof session.error?.code === "string" ? session.error.code : undefined;
  const errorDetail = typeof session.error?.detail === "string" ? session.error.detail : undefined;
  const attemptCount = stream.attempt ?? session.attempt_count;
  const attemptLabel = attemptCount > 1 ? `Attempt ${attemptCount}` : null;
  const cardProposal = revealed ?? partial;
  const cardReady = Boolean(
    cardProposal && (cardProposal.title || cardProposal.lines?.length || cardProposal.steps?.length),
  );
  const showRail = streaming || stream.nodes.length > 0;
  const previous =
    streaming && session.proposal && session.attempt_count > 0 ? session.proposal : null;
  const adjustment = stream.violations.at(-1)?.message;
  const streamError = stream.error;
  const retryAfter = retrySeconds(actionError?.problem.extra?.retry_after ?? session.error?.retry_after);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <p className="mb-4 max-w-prose text-sm leading-relaxed text-muted-foreground">
        “{session.sentence}”
      </p>

      {showRail || streaming || session.status === "awaiting_user" ? (
        <div
          className={
            showRail
              ? "grid items-start gap-6 lg:grid-cols-[11.5rem_minmax(0,1fr)]"
              : undefined
          }
        >
          {showRail ? (
            <ProgressRail
              nodes={stream.nodes}
              settled={session.status === "awaiting_user"}
              note={
                stream.phase === "polling"
                  ? "The live update dropped. Checking the proposal."
                  : adjustment
                    ? `Adjusted: ${adjustment}`
                    : null
              }
            />
          ) : null}
          <div>
            {previous && previous.title !== cardProposal?.title ? (
              <p className="mb-3 text-sm text-muted-foreground opacity-60">
                Previous: {previous.title}
              </p>
            ) : null}
            {cardReady && cardProposal ? (
              <ProposalCard
                key={`${attemptCount}-${cardProposal.title ?? "partial"}`}
                proposal={cardProposal}
                pantry={pantry}
                attemptLabel={attemptLabel}
                stale={stale}
                staleMessage={staleOverride ?? undefined}
                busy={busy}
                showActions={session.status === "awaiting_user"}
                onConfirm={(acknowledgeExpired) => {
                  if (!session.proposal_etag) return;
                  setActionError(null);
                  confirm.mutate({ etag: session.proposal_etag, acknowledgeExpired });
                }}
                onRevise={(note) => revise.mutate(note)}
                onAbandon={() => abandon.mutate()}
                onRepropose={() => revise.mutate(REPROPOSE_NOTE)}
              />
            ) : streaming ? (
              <ProposalSkeleton />
            ) : null}
          </div>
        </div>
      ) : null}

      {failed ? (
        <CookErrorCard
          key={`${errorCode ?? "failed"}-${retryAfter ?? "now"}`}
          code={actionError?.problem.code ?? streamError?.code ?? errorCode}
          detail={actionError?.problem.detail ?? streamError?.detail ?? errorDetail}
          retryAfter={retryAfter}
          pending={busy}
          onRecover={() => {
            if (actionError) recoverFrom(actionError, session.sentence);
            else if (session.error) {
              recoverFrom(
                new ApiError({
                  type: "about:blank",
                  title: "Cook failed",
                  status: 422,
                  detail: errorDetail || "The cook session failed.",
                  instance: `/api/cook/${id}`,
                  code: errorCode || "cook_failed",
                  request_id: "",
                }),
                session.sentence,
              );
            }
          }}
        />
      ) : null}

      {session.status === "awaiting_user" && actionError && actionError.problem.code !== "stale_proposal" ? (
        <div className="mt-4">
          <CookErrorCard
            key={`${actionError.problem.code}-${retryAfter ?? "now"}`}
            code={actionError.problem.code}
            detail={actionError.problem.detail}
            retryAfter={retryAfter}
            pending={busy}
            onRecover={() => recoverFrom(actionError, session.sentence)}
          />
        </div>
      ) : null}

      {session.status === "awaiting_user" && !session.proposal && !cardProposal && !failed ? (
        <CookErrorCard
          detail="The session is waiting, but the proposal didn't come back."
          pending={busy}
          onRecover={() => router.push(`/cook?sentence=${encodeURIComponent(session.sentence)}`)}
        />
      ) : null}

      {session.status === "committed" ? (
        <div className="max-w-md">
          <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">
            {session.proposal?.title ?? "Cooked"}
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            This proposal was confirmed. The pantry already reflects what it used.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {session.meal_id ? (
              <Button asChild className="h-11 lg:h-9">
                <Link href={`/meals/${session.meal_id}`}>View meal</Link>
              </Button>
            ) : null}
            <Button asChild variant="ghost" className="h-11 lg:h-9">
              <Link href="/cook">Cook again</Link>
            </Button>
          </div>
        </div>
      ) : null}

      {session.status === "abandoned" ? (
        <div className="max-w-md">
          <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">Abandoned</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            This proposal was set aside. The pantry was left as it was.
          </p>
          <Button asChild className="mt-4 h-11 lg:h-9">
            <Link href="/cook">Cook something else</Link>
          </Button>
        </div>
      ) : null}
    </div>
  );
}
