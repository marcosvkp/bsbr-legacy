"use client";

import Link from "next/link";

export type AdminTab = "qualification" | "suggestions" | "reweight" | "batch";

const TABS: Array<{ id: AdminTab; label: string }> = [
  { id: "qualification", label: "Qualificação" },
  { id: "suggestions", label: "Sugestões de mapas" },
  { id: "reweight", label: "Reweight" },
  { id: "batch", label: "Batch" },
];

/** Barra de abas do admin — navegação por URL (?tab=...). */
export function AdminTabs({ active }: { active: AdminTab }) {
  return (
    <div
      role="tablist"
      aria-label="Administração"
      className="flex w-fit max-w-full flex-wrap gap-1 rounded-lg border border-border-subtle bg-surface p-1"
    >
      {TABS.map((tab) => (
        <Link
          key={tab.id}
          role="tab"
          aria-selected={active === tab.id}
          href={tab.id === "qualification" ? "/admin" : `/admin?tab=${tab.id}`}
          className={`rounded-md px-4 py-1.5 text-sm font-bold transition-colors ${
            active === tab.id
              ? "bg-secondary text-white shadow-[0_0_12px_var(--glow-secondary)]"
              : "text-muted hover:text-foreground"
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
