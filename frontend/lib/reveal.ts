import type { ProposalView } from "@/components/cook/proposal-card";

export function proposalUnitCount(proposal: ProposalView): number {
  return (
    (proposal.title ? 1 : 0) +
    (proposal.servings ? 1 : 0) +
    (proposal.lines?.length ?? 0) +
    (proposal.steps?.length ?? 0)
  );
}

/** Reveal title, then servings, then each line, then each step. */
export function sliceProposal(proposal: ProposalView, units: number): ProposalView {
  let left = Math.max(0, units);
  const next: ProposalView = {};
  if (proposal.title && left > 0) {
    next.title = proposal.title;
    next.rationale = proposal.rationale;
    left -= 1;
  }
  if (proposal.servings && left > 0) {
    next.servings = proposal.servings;
    left -= 1;
  }
  const lines = proposal.lines ?? [];
  if (left > 0 && lines.length > 0) {
    next.lines = lines.slice(0, left);
    left -= next.lines.length;
  }
  const steps = proposal.steps ?? [];
  if (left > 0 && steps.length > 0) {
    next.steps = steps.slice(0, left);
  }
  return next;
}

export function proposalFromTokens(buffer: string): ProposalView | null {
  if (!buffer) return null;
  const title = /"title"\s*:\s*"((?:\\.|[^"\\])*)"/.exec(buffer);
  const servings = /"servings"\s*:\s*(\d+)/.exec(buffer);
  if (!title && !servings) return null;
  const view: ProposalView = {};
  if (title?.[1]) {
    view.title = title[1].replace(/\\"/g, '"').replace(/\\n/g, " ");
  }
  if (servings?.[1]) {
    const value = Number(servings[1]);
    if (value >= 1 && value <= 24) view.servings = value;
  }
  return view;
}
