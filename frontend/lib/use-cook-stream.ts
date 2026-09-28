"use client";

import { useEffect, useRef, useState } from "react";

import type { ProposalView } from "@/components/cook/proposal-card";
import {
  ApiError,
  cookSessionSchema,
  cookStreamUrl,
  getCook,
  proposalSchema,
  type CookSession,
} from "@/lib/api";

/** Initial connection plus this many reconnects, then poll. */
export const STREAM_RECONNECTS = 3;
export const STREAM_BACKOFF_MS = [400, 800, 1600];
export const STREAM_POLL_MS = 2000;

export type CookStreamPhase = "idle" | "connecting" | "live" | "polling" | "done";

export type CookStreamViolation = {
  code: string;
  message: string;
};

export type CookStreamState = {
  phase: CookStreamPhase;
  nodes: string[];
  proposal: ProposalView | null;
  tokens: string;
  violations: CookStreamViolation[];
  error: { code?: string; detail?: string } | null;
  session: CookSession | null;
  attempt: number | null;
};

const INITIAL: CookStreamState = {
  phase: "idle",
  nodes: [],
  proposal: null,
  tokens: "",
  violations: [],
  error: null,
  session: null,
  attempt: null,
};

const EVENT_NAMES = [
  "node_started",
  "constraints",
  "proposal_token",
  "proposal",
  "violation",
  "awaiting_user",
  "error",
  "busy",
  "done",
] as const;

function record(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object") return null;
  return value as Record<string, unknown>;
}

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

export function useCookStream(
  sessionId: string,
  enabled: boolean,
  onSession?: (session: CookSession) => void,
): CookStreamState {
  const [state, setState] = useState<CookStreamState>(INITIAL);
  const onSessionRef = useRef(onSession);
  onSessionRef.current = onSession;

  useEffect(() => {
    if (!enabled || !sessionId) return;

    let cancelled = false;
    let source: EventSource | null = null;
    let failures = 0;
    let busyRetries = 0;
    let sawBusy = false;
    let finished = false;
    let retryTimer = 0;
    let pollTimer = 0;

    function adopt(session: CookSession) {
      if (cancelled) return;
      onSessionRef.current?.(session);
      const code = typeof session.error?.code === "string" ? session.error.code : undefined;
      const detail = typeof session.error?.detail === "string" ? session.error.detail : undefined;
      setState((prev) => ({
        ...prev,
        session,
        proposal: (session.proposal as ProposalView | null) ?? prev.proposal,
        attempt: session.attempt_count,
        phase: "done",
        error: session.status === "failed" ? { code, detail } : prev.error,
      }));
    }

    function handle(eventName: string, raw: string) {
      if (cancelled || finished) return;
      const data = parseJson(raw);
      const body = record(data);

      if (eventName === "node_started" && typeof body?.node === "string") {
        const node = body.node;
        setState((prev) => ({ ...prev, phase: "live", nodes: [...prev.nodes, node] }));
        return;
      }
      if (eventName === "proposal_token" && typeof body?.text === "string" && body.text) {
        const text = body.text;
        setState((prev) => ({ ...prev, phase: "live", tokens: prev.tokens + text }));
        return;
      }
      if (eventName === "proposal") {
        const parsed = proposalSchema.safeParse(data);
        if (parsed.success) {
          setState((prev) => ({ ...prev, phase: "live", proposal: parsed.data }));
        }
        return;
      }
      if (
        eventName === "violation" &&
        typeof body?.code === "string" &&
        typeof body.message === "string"
      ) {
        const violation = { code: body.code, message: body.message };
        setState((prev) => ({ ...prev, violations: [...prev.violations, violation] }));
        return;
      }
      if (eventName === "awaiting_user" && typeof body?.attempt === "number") {
        const attempt = body.attempt;
        setState((prev) => ({ ...prev, attempt }));
        return;
      }
      if (eventName === "error") {
        setState((prev) => ({
          ...prev,
          error: {
            code: typeof body?.code === "string" ? body.code : undefined,
            detail: typeof body?.detail === "string" ? body.detail : undefined,
          },
        }));
        return;
      }
      if (eventName === "busy") {
        sawBusy = true;
        return;
      }
      if (eventName === "done") {
        finished = true;
        source?.close();
        const parsed = cookSessionSchema.safeParse(body?.session);
        if (parsed.success) {
          adopt(parsed.data);
          return;
        }
        void getCook(sessionId)
          .then((session) => adopt(session))
          .catch(() => {
            if (!cancelled) setState((prev) => ({ ...prev, phase: "done" }));
          });
      }
    }

    function startPolling() {
      if (cancelled || finished) return;
      setState((prev) => ({ ...prev, phase: "polling" }));
      void pollOnce();
    }

    async function pollOnce() {
      if (cancelled || finished) return;
      try {
        const session = await getCook(sessionId);
        if (cancelled || finished) return;
        if (session.status !== "running") {
          finished = true;
          adopt(session);
          return;
        }
        setState((prev) => ({ ...prev, phase: "polling", session }));
      } catch (error) {
        if (error instanceof ApiError && error.problem.status === 404) {
          finished = true;
          setState((prev) => ({
            ...prev,
            phase: "done",
            error: { code: error.problem.code, detail: error.problem.detail },
          }));
          return;
        }
      }
      if (!cancelled && !finished) {
        pollTimer = window.setTimeout(() => void pollOnce(), STREAM_POLL_MS);
      }
    }

    function connect() {
      if (cancelled || finished) return;
      source = new EventSource(cookStreamUrl(sessionId));
      setState((prev) => ({
        ...prev,
        phase: prev.nodes.length > 0 || prev.proposal ? "live" : "connecting",
      }));
      for (const name of EVENT_NAMES) {
        source.addEventListener(name, (event) => {
          if (event instanceof MessageEvent && typeof event.data === "string") {
            handle(name, event.data);
          }
        });
      }
      source.onerror = () => {
        source?.close();
        if (cancelled || finished) return;
        if (sawBusy) {
          sawBusy = false;
          busyRetries += 1;
          if (busyRetries > 20) {
            startPolling();
            return;
          }
          retryTimer = window.setTimeout(connect, 500);
          return;
        }
        failures += 1;
        if (failures > STREAM_RECONNECTS) {
          startPolling();
          return;
        }
        const delay = STREAM_BACKOFF_MS[failures - 1] ?? STREAM_BACKOFF_MS.at(-1) ?? 1600;
        retryTimer = window.setTimeout(connect, delay);
      };
    }

    setState({ ...INITIAL, phase: "connecting" });
    connect();

    return () => {
      cancelled = true;
      finished = true;
      source?.close();
      window.clearTimeout(retryTimer);
      window.clearTimeout(pollTimer);
    };
  }, [enabled, sessionId]);

  if (!enabled && state.phase !== "done") return INITIAL;
  return state;
}
