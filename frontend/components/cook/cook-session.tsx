"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { CookErrorCard } from "@/components/cook/cook-error";
import { ProposalSkeleton } from "@/components/cook/cook-skeleton";
import { ProposalCard, type PantryAmount } from "@/components/cook/proposal-card";
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

const REPROPOSE_NOTE = "The pantry changed. Propose again from what's there now.";

export function CookSessionView({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [staleOverride, setStaleOverride] = useState<string | null>(null);
  const [actionError, setActionError] = useState<ApiError | null>(null);

  const sessionQuery = useQuery({
    queryKey: ["cook", id],
    queryFn: () => getCook(id),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
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
    mutationFn: (note: string) => reviseCook(id, note),
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
    mutationFn: (etag: string) => confirmCook(id, etag),
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
    mutationFn: (sentence: string) => startCook(sentence),
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
    pantry[item.id] = { name: item.name, quantity: item.quantity, unit: item.unit };
  }

  const stale = Boolean(staleOverride) || session.stale;
  const failed = session.status === "failed";
  const errorCode = typeof session.error?.code === "string" ? session.error.code : undefined;
  const errorDetail = typeof session.error?.detail === "string" ? session.error.detail : undefined;
  const attemptLabel =
    session.attempt_count > 1 ? `Attempt ${session.attempt_count}` : null;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <p className="mb-4 max-w-prose text-sm leading-relaxed text-muted-foreground">
        “{session.sentence}”
      </p>

      {session.status === "running" ? <ProposalSkeleton /> : null}

      {failed ? (
        <CookErrorCard
          code={actionError?.problem.code ?? errorCode}
          detail={actionError?.problem.detail ?? errorDetail}
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

      {session.status === "awaiting_user" && session.proposal ? (
        <>
          {actionError && actionError.problem.code !== "stale_proposal" ? (
            <div className="mb-4">
              <CookErrorCard
                code={actionError.problem.code}
                detail={actionError.problem.detail}
                pending={busy}
                onRecover={() => recoverFrom(actionError, session.sentence)}
              />
            </div>
          ) : null}
          <ProposalCard
            key={`${session.attempt_count}-${session.proposal.title}`}
            proposal={session.proposal}
            pantry={pantry}
            attemptLabel={attemptLabel}
            stale={stale}
            staleMessage={staleOverride ?? undefined}
            busy={busy}
            onConfirm={() => {
              if (!session.proposal_etag) return;
              setActionError(null);
              confirm.mutate(session.proposal_etag);
            }}
            onRevise={(note) => revise.mutate(note)}
            onAbandon={() => abandon.mutate()}
            onRepropose={() => revise.mutate(REPROPOSE_NOTE)}
          />
        </>
      ) : null}

      {session.status === "awaiting_user" && !session.proposal && !failed ? (
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
