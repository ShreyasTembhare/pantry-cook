"use client";

import { useEffect, useState } from "react";

import type { ProposalView } from "@/components/cook/proposal-card";
import { useReducedMotion } from "@/components/cook/progress-rail";
import { proposalUnitCount, sliceProposal } from "@/lib/reveal";

export function useRevealedProposal(
  proposal: ProposalView | null,
  animate: boolean,
): ProposalView | null {
  const reduced = useReducedMotion();
  const total = proposal ? proposalUnitCount(proposal) : 0;
  const title = proposal?.title ?? "";
  const [units, setUnits] = useState(0);

  useEffect(() => {
    let shown = 0;
    let interval = 0;
    const kick = window.setTimeout(() => {
      if (!animate || reduced || total <= 1) {
        setUnits(total);
        return;
      }
      shown = 1;
      setUnits(1);
      interval = window.setInterval(() => {
        shown += 1;
        setUnits(Math.min(total, shown));
        if (shown >= total) window.clearInterval(interval);
      }, 120);
    }, 0);
    return () => {
      window.clearTimeout(kick);
      window.clearInterval(interval);
    };
  }, [animate, reduced, title, total]);

  if (!proposal || total === 0) return proposal;
  if (!animate || reduced) return proposal;
  return sliceProposal(proposal, units);
}
