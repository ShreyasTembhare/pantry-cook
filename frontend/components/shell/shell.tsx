"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, ChefHat, MessageCircle, Moon, Package, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useSyncExternalStore, type ComponentType, type ReactNode } from "react";

import { Pip } from "@/components/mascot/pip";
import { getHealth, listCookSessions } from "@/lib/api";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Chat", icon: MessageCircle },
  { href: "/pantry", label: "Pantry", icon: Package },
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
        "flex min-h-11 min-w-14 flex-col items-center justify-center gap-1 py-2 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        active ? "text-primary" : "text-muted-foreground",
      )}
    >
      <Icon className="h-5 w-5" strokeWidth={1.75} />
      <span>{label}</span>
    </Link>
  );
}

function useMounted() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const dark = mounted && resolvedTheme === "dark";
  return (
    <button
      type="button"
      className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
      aria-label={dark ? "Use light theme" : "Use dark theme"}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
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
    <div data-app-shell className="flex h-full flex-col lg:flex-row">
      <aside
        data-app-chrome
        className="hidden border-border/70 bg-background/70 backdrop-blur lg:flex lg:w-64 lg:flex-col lg:border-r"
      >
        <div className="flex items-center gap-3 px-5 pt-5">
          <Pip className="h-12 w-10" />
          <div>
            <h1 className="font-serif text-lg font-semibold tracking-tight">Pantry Cook</h1>
            <p className="text-xs text-muted-foreground">Pip, your kitchen chef</p>
            {demoChef ? (
              <div className="mt-2">
                <DemoBadge />
              </div>
            ) : null}
          </div>
        </div>
        <nav aria-label="Primary" className="flex flex-1 flex-col gap-1 px-3 py-4">
          {navItems.map((item) => (
            <NavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </nav>
        <div className="flex items-center justify-between gap-2 px-3 pb-5">
          {latest ? (
            <UnfinishedPill href={`/cook/${latest.id}`} sentence={latest.sentence} count={unfinished.length} />
          ) : (
            <span />
          )}
          <ThemeToggle />
        </div>
      </aside>

      <div data-app-column className="flex min-h-0 flex-1 flex-col">
        <header
          data-app-chrome
          className="flex min-h-14 items-center justify-between gap-3 border-b border-border px-4 py-2 lg:hidden"
        >
          <div className="flex items-center gap-2">
            <Pip className="h-9 w-8" />
            <h1 className="font-serif text-lg font-semibold tracking-tight">Pantry Cook</h1>
            {demoChef ? <DemoBadge /> : null}
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {latest ? (
              <UnfinishedPill href={`/cook/${latest.id}`} sentence={latest.sentence} count={unfinished.length} />
            ) : null}
          </div>
        </header>

        <main
          className={cn(
            "flex min-h-0 flex-1 flex-col",
            pathname === "/" ? "overflow-hidden" : "overflow-y-auto",
          )}
        >
          {children}
        </main>

        <nav
          data-app-chrome
          aria-label="Mobile"
          className="flex items-center justify-around border-t border-border bg-background pb-safe lg:hidden"
        >
          {navItems.map((item) => (
            <MobileNavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </nav>
      </div>
    </div>
  );
}
