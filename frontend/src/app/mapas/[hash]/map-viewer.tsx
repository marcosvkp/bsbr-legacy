"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { MapDetail } from "@/lib/types";
import { formatAcc, formatDateTime, formatInt, formatNumber, formatPp } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { PlayerAvatar } from "@/components/player-avatar";
import { SubStats } from "@/components/sub-stats";

const DIFF_ORDER: Record<string, number> = {
  Easy: 1,
  Normal: 2,
  Hard: 3,
  Expert: 4,
  ExpertPlus: 5,
};

/** Difficulty mais alta da lista (a lista vem ordenada do backend, mas reforça aqui). */
function highestFirst(diffs: MapDetail["difficulties_detail"]): MapDetail["difficulties_detail"] {
  return [...diffs].sort((a, b) => (DIFF_ORDER[b.name] ?? 0) - (DIFF_ORDER[a.name] ?? 0));
}

function Arrow({ after, before }: { after: number | null; before: number | null }) {
  if (after === null || before === null || after === before) {
    return <span aria-hidden="true" className="text-muted">→</span>;
  }
  return (
    <span aria-hidden="true" className={`font-bold ${after > before ? "text-success" : "text-danger"}`}>
      {after > before ? "↑" : "↓"}
    </span>
  );
}

interface MapViewerProps {
  map: MapDetail;
}

export function MapViewer({ map }: MapViewerProps) {
  const diffs = useMemo(() => highestFirst(map.difficulties_detail), [map.difficulties_detail]);
  const [selected, setSelected] = useState<string | null>(null);
  // Padrão: dificuldade mais alta
  const activeName = selected ?? diffs[0]?.name ?? null;
  const active = diffs.find((d) => d.name === activeName) ?? null;
  const maxPpByName = new Map(map.difficulties.map((d) => [d.name, d.max_pp]));

  const leaderboard = useMemo(() => {
    if (!activeName) return map.leaderboard;
    return map.leaderboard.filter((entry) => entry.difficulty === activeName);
  }, [map.leaderboard, activeName]);

  if (diffs.length === 0) {
    return (
      <p className="py-4 text-sm text-muted">Nenhuma dificuldade rankeada.</p>
    );
  }

  return (
    <>
      {/* Seletor de dificuldade */}
      <div role="tablist" aria-label="Selecionar dificuldade" className="flex flex-wrap gap-1.5">
        {diffs.map((diff) => {
          const isActive = diff.name === activeName;
          return (
            <button
              key={diff.name}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setSelected(diff.name)}
              className={
                isActive
                  ? "rounded-md border border-accent bg-accent/15 px-3 py-1.5 text-sm font-bold text-white shadow-[0_0_12px_var(--glow-accent)]"
                  : "rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-semibold text-muted transition-colors hover:border-accent/50 hover:text-foreground"
              }
            >
              {diff.name}
              <span className="ml-2 font-black tabular-nums">
                {formatNumber(diff.total_stars)}
              </span>
            </button>
          );
        })}
      </div>

      {active ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border-subtle bg-background/40 p-3.5 sm:flex-row sm:items-center sm:gap-5">
          <div className="flex w-full items-center gap-3 sm:w-64">
            <Badge variant={active.name === "ExpertPlus" ? "accent" : "default"}>
              {active.name}
            </Badge>
            <span className="text-2xl font-black tabular-nums">{formatNumber(active.total_stars)}</span>
            <span className="text-sm text-muted">máx {formatInt(maxPpByName.get(active.name) ?? 0)} PP</span>
          </div>
          <div className="w-full sm:max-w-xs">
            <SubStats
              acc={active.acc_stars}
              tech={active.tech_stars}
              speed={active.speed_stars}
              format={(v) => (v != null ? formatNumber(v) : "—")}
            />
          </div>
        </div>
      ) : null}

      {/* Leaderboard filtrado pela dificuldade selecionada */}
      <div className="overflow-x-auto">
        {leaderboard.length === 0 ? (
          <p className="py-4 text-sm text-muted">
            Nenhuma pontuação registrada para {activeName}.
          </p>
        ) : (
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left text-[11px] uppercase tracking-wider text-muted">
                <th scope="col" className="py-2.5 pr-3 font-bold">#</th>
                <th scope="col" className="py-2.5 pr-3 font-bold">Jogador</th>
                <th scope="col" className="hidden py-2.5 pr-3 text-right font-bold md:table-cell">Score</th>
                <th scope="col" className="py-2.5 pr-3 text-right font-bold">Acc</th>
                <th scope="col" className="py-2.5 pr-3 text-center font-bold">FC</th>
                <th scope="col" className="py-2.5 pr-3 text-right font-bold">PP</th>
                <th scope="col" className="hidden py-2.5 text-right font-bold xl:table-cell">Decomposição</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((entry, index) => (
                <tr
                  key={`${entry.player_name}-${entry.difficulty}-${index}`}
                  className="border-b border-border-subtle/50 last:border-b-0"
                  style={index % 2 === 1 ? { background: "rgba(255,255,255,0.012)" } : undefined}
                >
                  <td className="py-2.5 pr-3 font-bold tabular-nums text-muted">
                    {index + 1}
                  </td>
                  <td className="py-2.5 pr-3 font-medium">
                    {entry.player_ss_id ? (
                      <Link
                        href={`/jogadores/${entry.player_ss_id}`}
                        className="group flex items-center gap-2.5"
                      >
                        <PlayerAvatar name={entry.player_name} avatarUrl={entry.avatar_url} size={28} />
                        <span className="transition-colors group-hover:text-secondary">
                          {entry.player_name}
                        </span>
                      </Link>
                    ) : (
                      <span className="flex items-center gap-2.5">
                        <PlayerAvatar name={entry.player_name} avatarUrl={entry.avatar_url} size={28} />
                        {entry.player_name}
                      </span>
                    )}
                  </td>
                  <td className="hidden py-2.5 pr-3 text-right tabular-nums md:table-cell">
                    {formatInt(entry.score)}
                  </td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{formatAcc(entry.acc)}</td>
                  <td className="py-2.5 pr-3 text-center">
                    {entry.full_combo ? (
                      <Badge variant="success">FC</Badge>
                    ) : (
                      <span className="text-muted/40">—</span>
                    )}
                  </td>
                  <td className="py-2.5 pr-3 text-right text-[15px] font-bold tabular-nums">
                    {formatPp(entry.pp)}
                  </td>
                  <td className="hidden py-2.5 text-right xl:table-cell">
                    <div className="ml-auto w-52">
                      <SubStats
                        acc={entry.pp_acc}
                        tech={entry.pp_tech}
                        speed={entry.pp_speed}
                        size="sm"
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Histórico de rating da dificuldade selecionada */}
      <ul>
        {map.rating_history
          .filter((entry) => !activeName || entry.difficulty_name === activeName)
          .map((entry, index) => (
            <li
              key={`${entry.applied_at}-${index}`}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border-subtle/60 py-2.5 text-sm last:border-b-0"
            >
              <span className="flex items-center gap-2 font-bold tabular-nums">
                <span className="text-muted">{formatNumber(entry.total_before)}</span>
                <Arrow after={entry.total_after} before={entry.total_before} />
                <span
                  className={
                    entry.total_after !== null && entry.total_before !== null && entry.total_after > entry.total_before
                      ? "text-success"
                      : entry.total_after !== null && entry.total_before !== null && entry.total_after < entry.total_before
                        ? "text-danger"
                        : ""
                  }
                >
                  {formatNumber(entry.total_after)}
                </span>
              </span>
              <span className="flex-1 text-muted">{entry.reason}</span>
              {/* suppressHydrationWarning: datas formatadas por fuso (server=UTC,
                  browser=local) — o client corrige o texto após a hidratação */}
              <span className="text-xs text-muted/70" suppressHydrationWarning>
                por {entry.applied_by} · {formatDateTime(entry.applied_at)}
              </span>
            </li>
          ))}
        {map.rating_history.filter((entry) => entry.difficulty_name === activeName).length === 0 ? (
          <p className="py-4 text-sm text-muted">
            Sem mudanças de rating registradas para {activeName}.
          </p>
        ) : null}
      </ul>
    </>
  );
}
