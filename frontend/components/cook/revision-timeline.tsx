import { REVISION_ORDER_LABEL, revisionHistory, type RevisionAttempt } from "@/lib/cook";

export function RevisionTimeline({ attempts }: { attempts: RevisionAttempt[] }) {
  const entries = revisionHistory(attempts);
  if (entries.length === 0) return null;

  return (
    <section
      aria-label={`Revision history, ${REVISION_ORDER_LABEL.toLocaleLowerCase()}`}
      className="mb-6"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Revision history
        </h2>
        <p className="text-xs text-muted-foreground">{REVISION_ORDER_LABEL}</p>
      </div>
      <ol className="mt-3 space-y-0 border-l border-border">
        {entries.map((entry, index) => (
          <li
            key={entry.attemptNo}
            aria-current={index === entries.length - 1 ? "step" : undefined}
            className="relative pb-4 pl-4 last:pb-0"
          >
            <span
              className="absolute top-1.5 -left-px size-1.5 -translate-x-1/2 rounded-full bg-primary"
              aria-hidden
            />
            <p className="text-xs text-muted-foreground tabular-nums">
              Attempt {entry.attemptNo}
              <span className="px-1.5" aria-hidden>
                ·
              </span>
              {entry.triggerLabel}
            </p>
            {entry.note ? (
              <p className="mt-1 text-sm leading-relaxed">
                <span className="text-muted-foreground">Note </span>“{entry.note}”
              </p>
            ) : null}
            <p className="mt-1 text-sm leading-relaxed">{entry.title}</p>
            {entry.opening ? (
              <p className="text-sm leading-relaxed text-muted-foreground">{entry.opening}</p>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
