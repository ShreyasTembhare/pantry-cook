"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Package, ChefHat, BookOpen } from "lucide-react";
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
  icon: React.ComponentType<{ className?: string }>;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        "lg:w-full",
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
      )}
    >
      <Icon className="h-5 w-5 shrink-0" />
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
  icon: React.ComponentType<{ className?: string }>;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex flex-col items-center gap-1 py-2 text-xs font-medium transition-colors min-w-[4rem]",
        active
          ? "text-primary"
          : "text-muted-foreground"
      )}
    >
      <Icon className="h-5 w-5" />
      <span>{label}</span>
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <aside className="hidden lg:flex lg:w-56 lg:flex-col lg:border-r lg:border-border">
        <div className="flex h-14 items-center px-5">
          <h1 className="font-serif text-lg font-semibold tracking-tight">
            Pantry Cook
          </h1>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3 py-2">
          {navItems.map((item) => (
            <NavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col min-h-0">
        <header className="flex h-14 items-center border-b border-border px-4 lg:hidden">
          <h1 className="font-serif text-lg font-semibold tracking-tight">
            Pantry Cook
          </h1>
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
