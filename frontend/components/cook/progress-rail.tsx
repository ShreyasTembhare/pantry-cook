"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

const STEPS = [
  ["load_pantry", "Reading pantry"],
  ["parse_sentence", "Understanding"],
  ["propose_meal", "Proposing"],
  ["validate_proposal", "Checking"],
] as const;

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);
  return reduced;
}

function useStagedCount(length: number, stepMs: number): number {
  const reduced = useReducedMotion();
  const [count, setCount] = useState(0);

  useEffect(() => {
    let shown = 0;
    let interval = 0;
    const push = (value: number) => setCount(value);
    const kick = window.setTimeout(() => {
      if (reduced || length === 0) {
        push(length);
        return;
      }
      shown = 1;
      push(Math.min(length, shown));
      interval = window.setInterval(() => {
        shown += 1;
        push(Math.min(length, shown));
        if (shown >= length) window.clearInterval(interval);
      }, stepMs);
    }, 0);
    return () => {
      window.clearTimeout(kick);
      window.clearInterval(interval);
    };
  }, [length, reduced, stepMs]);

  return count;
}

function stepState(
  id: string,
  nodes: string[],
  settled: boolean,
): "pending" | "active" | "done" {
  const order = STEPS.map(([step]) => step);
  let last = -1;
  for (const node of nodes) {
    const index = order.indexOf(node as (typeof order)[number]);
    if (index >= 0) last = index;
  }
  const index = order.indexOf(id as (typeof order)[number]);
  if (last < 0 || index < 0) return "pending";
  if (index < last || settled) return index <= last ? "done" : "pending";
  if (index === last) return settled ? "done" : "active";
  return "pending";
}

export function ProgressRail({
  nodes,
  settled = false,
  note,
}: {
  nodes: string[];
  settled?: boolean;
  note?: string | null;
}) {
  const count = useStagedCount(nodes.length, 220);
  const visible = nodes.slice(0, count);

  return (
    <div>
      <ol aria-label="Cook progress" className="flex flex-row flex-wrap gap-x-4 gap-y-2 lg:flex-col">
        {STEPS.map(([id, label]) => {
          const state = stepState(id, visible, settled && visible.length >= nodes.length);
          return (
            <li
              key={id}
              aria-current={state === "active" ? "step" : undefined}
              className={cn(
                "flex items-center gap-2 text-sm",
                state === "pending" && "text-muted-foreground/60",
                state === "active" && "font-medium text-foreground",
                state === "done" && "text-muted-foreground",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "size-1.5 shrink-0 rounded-sm",
                  state === "pending" && "bg-border",
                  state === "active" && "bg-primary",
                  state === "done" && "bg-primary/70",
                )}
              />
              {label}
            </li>
          );
        })}
      </ol>
      {note ? <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{note}</p> : null}
    </div>
  );
}

export { useReducedMotion };
