"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ComponentKey, RankingItem } from "@/lib/types";
import { formatPp } from "@/lib/format";
import { PlayerAvatar } from "@/components/player-avatar";
import { SubStats } from "@/components/sub-stats";

const COMPONENT_LABEL: Record<ComponentKey, string> = {
  total: "PP Total",
  acc: "PP Acc",
  tech: "PP Tech",
  speed: "PP Speed",
};

const RANK_STYLE: Record<number, { chip: string; text: string; glow: string; label: string }> = {
  1: {
    chip: "border-yellow-400/60 bg-yellow-400/15 text-yellow-300",
    text: "text-yellow-300",
    glow: "shadow-[0_0_14px_rgba(250,204,21,0.4)]",
    label: "ouro",
  },
  2: {
    chip: "border-zinc-300/50 bg-zinc-300/10 text-zinc-200",
    text: "text-zinc-200",
    glow: "shadow-[0_0_10px_rgba(212,212,216,0.3)]",
    label: "prata",
  },
  3: {
    chip: "border-amber-600/60 bg-amber-600/15 text-amber-500",
    text: "text-amber-500",
    glow: "shadow-[0_0_10px_rgba(217,119,6,0.35)]",
    label: "bronze",
  },
};

export interface RankingTableProps {
  items: RankingItem[];
  component: ComponentKey;
}

/**
 * Tabela do ranking com busca client-side por nome dentro da página carregada.
 */
export function RankingTable({ items, component }: RankingTableProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return items;
    return items.filter((item) => item.name.toLowerCase().includes(term));
  }, [items, query]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <div className="relative w-full max-w-xs">
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted/60"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar jogador…"
            aria-label="Buscar jogador por nome"
            className="h-9 w-full rounded-md border border-border-subtle bg-surface pl-9 pr-3 text-sm text-foreground placeholder:text-muted/60 focus:border-secondary focus:outline-none"
          />
        </div>
        <span className="ml-auto text-xs tabular-nums text-muted" aria-live="polite">
          {filtered.length} <span className="text-muted/60">de {items.length}</span>
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-subtle bg-background/50 text-left text-[11px] uppercase tracking-wider text-muted">
              <th scope="col" className="w-12 px-4 py-3 font-bold">#</th>
              <th scope="col" className="px-3 py-3 font-bold">Jogador</th>
              <th scope="col" className="px-3 py-3 text-right font-bold">
                {COMPONENT_LABEL[component]}
              </th>
              <th scope="col" className="hidden px-3 py-3 text-right font-bold md:table-cell">
                Acc · Tech · Speed
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item, index) => {
              const style = RANK_STYLE[item.rank];
              return (
                <tr
                  key={item.ss_id}
                  className="border-b border-border-subtle/50 transition-colors last:border-b-0 hover:bg-surface-2/40"
                  style={index % 2 === 1 ? { background: "rgba(255,255,255,0.012)" } : undefined}
                >
                  <td className="px-4 py-2.5">
                    {style ? (
                      <span
                        title={`${item.rank}º lugar (${style.label})`}
                        className={`inline-flex h-6 w-6 items-center justify-center rounded-md border text-xs font-bold tabular-nums ${style.chip} ${style.glow}`}
                      >
                        {item.rank}
                      </span>
                    ) : (
                      <span className="font-bold tabular-nums text-muted">{item.rank}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <Link
                      href={`/jogadores/${item.ss_id}`}
                      className="group flex items-center gap-3 rounded-md font-medium text-foreground"
                    >
                      <PlayerAvatar name={item.name} avatarUrl={item.avatar_url} size={32} />
                      <span className="truncate transition-colors group-hover:text-secondary">
                        {item.name}
                      </span>
                      <span className="shrink-0 rounded border border-border-subtle px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-muted">
                        {item.country}
                      </span>
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 text-right text-[15px] font-bold tabular-nums">
                    {formatPp(
                      component === "total"
                        ? item.pp_total
                        : component === "acc"
                          ? item.pp_acc
                          : component === "tech"
                            ? item.pp_tech
                            : item.pp_speed,
                    )}
                  </td>
                  <td className="hidden px-3 py-2.5 md:table-cell">
                    <div className="ml-auto max-w-56">
                      <SubStats
                        acc={item.pp_acc}
                        tech={item.pp_tech}
                        speed={item.pp_speed}
                        size="sm"
                      />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-muted">
            Nenhum jogador encontrado{query ? ` para “${query}”` : ""}.
          </p>
        ) : null}
      </div>
    </div>
  );
}
