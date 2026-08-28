"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/ranking", label: "Ranking" },
  { href: "/stars-ranking", label: "Stars" },
  { href: "/mapas", label: "Mapas" },
  { href: "/ao-vivo", label: "Ao Vivo" },
  { href: "/sobre", label: "Sobre" },
  { href: "/admin", label: "Admin" },
] as const;

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Navegação principal com destaque da rota ativa. */
export function SiteNav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Navegação principal" className="flex items-center gap-1 text-sm font-medium text-muted">
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`relative rounded-md px-3 py-1.5 transition-colors ${
              active
                ? "text-foreground after:absolute after:inset-x-2.5 after:-bottom-px after:h-0.5 after:rounded-full after:bg-accent after:shadow-[0_0_8px_var(--glow-accent)]"
                : "hover:bg-surface hover:text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
