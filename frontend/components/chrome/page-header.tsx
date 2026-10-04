import type { ReactNode } from "react";

export function PageHeader({ title, lede }: { title: string; lede?: ReactNode }) {
  return (
    <header className="mb-6">
      <h2 className="font-serif text-[1.75rem] leading-none tracking-tight">{title}</h2>
      {lede ? (
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">{lede}</p>
      ) : null}
    </header>
  );
}
