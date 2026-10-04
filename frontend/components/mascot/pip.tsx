"use client";

import { cn } from "@/lib/utils";

type PipProps = {
  mood?: "idle" | "thinking" | "happy";
  className?: string;
};

export function Pip({ mood = "idle", className }: PipProps) {
  const thinking = mood === "thinking";
  return (
    <svg
      viewBox="0 0 80 96"
      role="img"
      aria-label={thinking ? "Pip is thinking" : "Pip the leek"}
      className={cn("pip-bob h-16 w-14", thinking && "pip-think", className)}
    >
      <ellipse cx="40" cy="90" rx="16" ry="3" fill="oklch(0.4 0.02 60 / 0.18)" />
      <path
        d="M40 28c8 0 14 10 16 22 1 8-2 16-8 20-2 8-4 16-8 22-4-6-6-14-8-22-6-4-9-12-8-20 2-12 8-22 16-22z"
        fill="oklch(0.96 0.02 110)"
      />
      <path
        d="M40 30c2 8 2 16 0 24"
        stroke="oklch(0.88 0.04 120)"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M28 34c-10-16-6-28 2-32 6 8 8 18 6 28"
        fill="oklch(0.55 0.12 145)"
      />
      <path
        d="M40 30c2-18 10-28 18-30-2 12-6 22-12 28"
        fill="oklch(0.62 0.13 140)"
      />
      <path
        d="M34 18c-2-14 4-22 8-24 2 8 2 16 0 22"
        fill="oklch(0.48 0.11 150)"
      />
      <circle cx={thinking ? 32 : 33} cy={thinking ? 46 : 48} r="2.2" fill="oklch(0.28 0.02 60)" />
      <circle cx={thinking ? 48 : 47} cy={thinking ? 46 : 48} r="2.2" fill="oklch(0.28 0.02 60)" />
      {mood === "happy" ? (
        <path
          d="M34 56c2.5 3 9.5 3 12 0"
          fill="none"
          stroke="oklch(0.45 0.08 40)"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      ) : (
        <path
          d="M35 57h10"
          stroke="oklch(0.45 0.08 40)"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      )}
      {thinking ? (
        <g fill="oklch(0.45 0.08 145)">
          <circle cx="62" cy="24" r="2" />
          <circle cx="68" cy="18" r="1.4" />
          <circle cx="72" cy="12" r="1" />
        </g>
      ) : null}
    </svg>
  );
}
