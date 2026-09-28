"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cookErrorPresentation } from "@/lib/cook";

export function CookErrorCard({
  code,
  detail,
  retryAfter = null,
  pending = false,
  onRecover,
}: {
  code?: string;
  detail?: string;
  retryAfter?: number | null;
  pending?: boolean;
  onRecover: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  const [startedAt] = useState(() => Date.now());

  useEffect(() => {
    if (retryAfter === null || retryAfter <= 0) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [retryAfter]);

  const remaining =
    retryAfter === null
      ? null
      : Math.max(0, Math.ceil(retryAfter) - Math.floor((now - startedAt) / 1000));

  const presentation = cookErrorPresentation(code, detail, remaining);
  const waiting = code === "llm_rate_limited" && remaining !== null && remaining > 0;

  return (
    <div role="alert" className="rounded-lg border border-destructive/40 px-4 py-4">
      <h3 className="font-serif text-xl leading-tight tracking-tight">The proposal stopped</h3>
      <p className="mt-2 max-w-prose text-sm leading-relaxed">{presentation.message}</p>
      <Button
        type="button"
        className="mt-4 h-11 lg:h-9"
        onClick={onRecover}
        disabled={pending || waiting}
      >
        {pending ? "Working" : presentation.action}
      </Button>
    </div>
  );
}
