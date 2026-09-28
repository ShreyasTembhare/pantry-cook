"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, ChefHat, Package } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType, ReactNode } from "react";

import { getHealth, listCookSessions } from "@/lib/api";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Pantry", icon: Package },
  { href: "/cook", label: "Cook", icon: ChefHat },
  { href: "/meals", label: "Meals", icon: BookOpen },
] as const;

function NavLink({
  href,
  label,
  icon: Icon,
  active,
}: {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "lg:w-full",
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
      )}
    >
      <Icon className="h-5 w-5 shrink-0" strokeWidth={1.75} />
      <span className="hidden lg:inline">{label}</span>
    </Link>
  );
}

function MobileNavLink({
  href,
  label,
  icon: Icon,
  active,
}: {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex min-h-11 min-w-16 flex-col items-center justify-center gap-1 py-2 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        active ? "text-primary" : "text-muted-foreground",
      )}
    >
      <Icon className="h-5 w-5" strokeWidth={1.75} />
      <span>{label}</span>
    </Link>
  );
}

function DemoBadge() {
  return (
    <span className="inline-flex items-center rounded-md bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
      Demo chef
    </span>
  );
}

function UnfinishedPill({ href, sentence, count }: { href: string; sentence: string; count: number }) {
  const label = count > 1 ? `${count} unfinished proposals` : "Unfinished proposal";
  return (
    <Link
      href={href}
      title={sentence}
      className="inline-flex h-8 max-w-full items-center truncate rounded-full border border-warning/50 bg-warning/20 px-3 text-xs font-medium text-warning-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <span className="sm:hidden">{count > 1 ? `${count} unfinished` : "Unfinished"}</span>
      <span className="hidden sm:inline">{label}</span>
    </Link>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    staleTime: 60_000,
  });
  const unfinishedQuery = useQuery({
    queryKey: ["cook-sessions", "awaiting_user"],
    queryFn: () => listCookSessions("awaiting_user"),
    refetchInterval: 20_000,
  });

  const demoChef = healthQuery.data?.llm === "fake";
  const unfinished = unfinishedQuery.data ?? [];
  const latest = unfinished[0];

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <aside className="hidden lg:flex lg:w-56 lg:flex-col lg:border-r lg:border-border">
        <div className="px-5 pt-5">
          <h1 className="font-serif text-lg font-semibold tracking-tight">Pantry Cook</h1>
          {demoChef ? (
            <div className="mt-2">
              <DemoBadge />
            </div>
          ) : null}
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3 py-4">
          {navItems.map((item) => (
            <NavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </nav>
        {latest ? (
          <div className="px-3 pb-5">
            <UnfinishedPill href={`/cook/${latest.id}`} sentence={latest.sentence} count={unfinished.length} />
          </div>
        ) : null}
      </aside>

      <div className="flex min-h-0 flex-1 flex-col">
        <header className="flex min-h-14 items-center justify-between gap-3 border-b border-border px-4 py-2 lg:hidden">
          <div className="flex items-center gap-2">
            <h1 className="font-serif text-lg font-semibold tracking-tight">Pantry Cook</h1>
            {demoChef ? <DemoBadge /> : null}
          </div>
          {latest ? (
            <UnfinishedPill href={`/cook/${latest.id}`} sentence={latest.sentence} count={unfinished.length} />
          ) : null}
        </header>

        <main className="flex-1 overflow-y-auto">{children}</main>

        <nav className="flex items-center justify-around border-t border-border bg-background pb-safe lg:hidden">
          {navItems.map((item) => (
            <MobileNavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </nav>
      </div>
    </div>
  );
}
