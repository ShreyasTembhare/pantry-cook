import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getCook, type CookSession } from "@/lib/api";
import { STREAM_BACKOFF_MS, useCookStream } from "@/lib/use-cook-stream";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getCook: vi.fn() };
});

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  onerror: ((event: Event) => void) | null = null;
  private listeners = new Map<string, Set<(event: Event) => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    const bucket = this.listeners.get(type) ?? new Set();
    bucket.add(listener);
    this.listeners.set(type, bucket);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }

  fail() {
    this.onerror?.(new Event("error"));
  }
}

const proposal = {
  title: "Leeks on a plate",
  servings: 2,
  lines: [
    { kind: "use" as const, item_id: "leeks", quantity: "150", unit: "g" as const },
    { kind: "missing" as const, name: "olive oil", quantity_note: "a splash" },
  ],
  steps: ["Prep the leeks.", "Cook gently until just done."],
  rationale: "Uses the leeks while they are still good.",
};

const session: CookSession = {
  id: "sess-1",
  status: "awaiting_user",
  sentence: "something warm with the leeks",
  attempt_count: 1,
  proposal,
  proposal_etag: "a".repeat(64),
  violations: [],
  meal_id: null,
  error: null,
  stale: false,
  created_at: "2026-09-28T12:00:00",
  updated_at: "2026-09-28T12:00:01",
  expires_at: "2026-09-29T12:00:00",
};

describe("useCookStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.mocked(getCook).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("applies node, token, proposal, and done events in order", () => {
    const onSession = vi.fn();
    const { result } = renderHook(() => useCookStream("sess-1", true, onSession));
    const source = FakeEventSource.instances[0];
    expect(source?.url).toContain("/api/cook/sess-1/stream");

    act(() => {
      source?.emit("node_started", { node: "load_pantry" });
      source?.emit("node_started", { node: "propose_meal" });
      source?.emit("proposal_token", { text: '{"title":"Leeks' });
      source?.emit("proposal", proposal);
      source?.emit("awaiting_user", { attempt: 1 });
      source?.emit("done", { status: "awaiting_user", session });
    });

    expect(result.current.nodes).toEqual(["load_pantry", "propose_meal"]);
    expect(result.current.tokens).toContain("Leeks");
    expect(result.current.proposal?.title).toBe("Leeks on a plate");
    expect(result.current.attempt).toBe(1);
    expect(result.current.phase).toBe("done");
    expect(result.current.session?.proposal_etag).toBe(session.proposal_etag);
    expect(onSession).toHaveBeenCalledWith(expect.objectContaining({ id: "sess-1" }));
    expect(source?.closed).toBe(true);
  });

  it("reconnects three times and then polls the session", async () => {
    vi.useFakeTimers();
    vi.mocked(getCook).mockResolvedValue(session);
    const { result } = renderHook(() => useCookStream("sess-1", true));

    for (const delay of STREAM_BACKOFF_MS) {
      act(() => {
        FakeEventSource.instances.at(-1)?.fail();
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(delay);
      });
    }

    expect(FakeEventSource.instances).toHaveLength(STREAM_BACKOFF_MS.length + 1);
    act(() => {
      FakeEventSource.instances.at(-1)?.fail();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(getCook).toHaveBeenCalledWith("sess-1");
    expect(result.current.phase).toBe("done");
    expect(result.current.session?.status).toBe("awaiting_user");
    expect(result.current.proposal?.title).toBe("Leeks on a plate");
    expect(FakeEventSource.instances).toHaveLength(STREAM_BACKOFF_MS.length + 1);
  });
});
