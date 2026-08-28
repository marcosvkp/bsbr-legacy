import type { Metadata } from "next";
import Link from "next/link";
import { ApiError, getJson } from "@/lib/api";
import {
  type PlayerDetail,
  type PlayerScoresResponse,
  type RankingsResponse,
  RANKING_COUNTRY,
  weightedAt,
} from "@/lib/types";
import { formatAcc, formatInt, formatPp } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BackendOffline, EmptyState } from "@/components/empty-state";
import { PlayerAvatar } from "@/components/player-avatar";
import { SubStats } from "@/components/sub-stats";
import { buildHref } from "@/components/pagination";
import { SmartImg } from "@/components/smart-img";
import { RadarChart } from "./radar-chart";
import { EvolutionChart } from "./evolution-chart";
import { Calculator } from "./calculator";

export const metadata: Metadata = {
  title: "Jogador",
};


const TABLE_PAGE_SIZE = 25;

interface ProfileData {
  player: PlayerDetail;
  leaders: Record<string, number | null>;
  gainPps: number[];
  scores: PlayerScoresResponse | null;
}

async function loadProfile(ssId: string, scoresPage: number): Promise<
  | { ok: true; data: ProfileData }
  | { ok: false; status: number | null }
> {
  try {
    const [player, leadersAcc, leadersTech, leadersSpeed, gainScores, scores] = await Promise.all([
      getJson<PlayerDetail>(`/players/${encodeURIComponent(ssId)}`),
      getJson<RankingsResponse>(`/rankings?component=acc&page=1&page_size=1&country=${RANKING_COUNTRY}`).catch(() => null),
      getJson<RankingsResponse>(`/rankings?component=tech&page=1&page_size=1&country=${RANKING_COUNTRY}`).catch(() => null),
      getJson<RankingsResponse>(`/rankings?component=speed&page=1&page_size=1&country=${RANKING_COUNTRY}`).catch(() => null),
      getJson<PlayerScoresResponse>(`/players/${encodeURIComponent(ssId)}/scores?page=1&page_size=50`).catch(() => null),
      getJson<PlayerScoresResponse>(`/players/${encodeURIComponent(ssId)}/scores?page=${scoresPage}&page_size=${TABLE_PAGE_SIZE}`).catch(() => null),
    ]);

    const leaders: Record<string, number | null> = {
      acc: leadersAcc?.items[0]?.pp_acc ?? null,
      tech: leadersTech?.items[0]?.pp_tech ?? null,
      speed: leadersSpeed?.items[0]?.pp_speed ?? null,
    };
    const gainPps = (gainScores?.items ?? [])
      .map((score) => score.pp)
      .filter((pp): pp is number => pp !== null);

    return { ok: true, data: { player, leaders, gainPps, scores } };
  } catch (cause) {
    return { ok: false, status: cause instanceof ApiError ? cause.status : null };
  }
}

function StatBlock({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex flex-col rounded-lg border border-border-subtle/70 bg-background/60 px-3 py-2.5">
      <span className="text-[10px] font-bold uppercase tracking-widest text-muted">{label}</span>
      <span className={`text-xl font-bold tabular-nums ${accent ? "text-secondary" : ""}`}>
        {value}
      </span>
    </div>
  );
}

export default async function PlayerPage(props: PageProps<"/jogadores/[ss_id]">) {
  const { ss_id: ssId } = await props.params;
  const searchParams = await props.searchParams;
  const pageParam = Array.isArray(searchParams.page) ? searchParams.page[0] : searchParams.page;
  const scoresPageRaw = Number.parseInt(pageParam ?? "1", 10);
  const scoresPage = Number.isFinite(scoresPageRaw) && scoresPageRaw >= 1 ? scoresPageRaw : 1;

  const result = await loadProfile(ssId, scoresPage);
  if (!result.ok) {
    if (result.status === 404) {
      return (
        <EmptyState
          title="Jogador não encontrado"
          description={`Nenhum jogador com o id ${ssId}.`}
        />
      );
    }
    return <BackendOffline what="o perfil do jogador" />;
  }

  const { player, leaders, gainPps, scores } = result.data;

  const radarPlayer: Record<string, number | null> = {
    acc: player.pp_acc,
    tech: player.pp_tech,
    speed: player.pp_speed,
  };

  const scoresOffset = scores ? (scores.page - 1) * scores.page_size : 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Cabeçalho do jogador */}
      <section className="relative overflow-hidden rounded-xl border border-border-subtle bg-surface">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 55% 120% at 12% -20%, rgba(239,68,68,0.16), transparent 60%)," +
              "radial-gradient(ellipse 45% 110% at 90% 120%, rgba(59,130,246,0.14), transparent 60%)",
          }}
        />
        <div className="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center">
          <div className="relative shrink-0">
            <div
              aria-hidden="true"
              className="absolute -inset-1.5 rounded-full bg-gradient-to-tr from-accent/40 via-transparent to-secondary/40 blur-[2px]"
            />
            <PlayerAvatar name={player.name} avatarUrl={player.avatar_url} size={88} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="font-display text-3xl font-extrabold uppercase tracking-tight">
                {player.name}
              </h1>
              <Badge variant="secondary">{player.country}</Badge>
              {player.rank !== null ? (
                <Badge variant="accent">#{formatInt(player.rank)} BR</Badge>
              ) : null}
            </div>
            <p className="mt-1.5 text-sm text-muted">
              <Link href="/ranking" className="transition-colors hover:text-secondary">
                Ranking BSBR
              </Link>
              <span className="mx-1.5 text-muted/50">·</span>
              <span className="font-mono text-xs">{player.ss_id}</span>
            </p>
          </div>
          <div className="grid w-full grid-cols-2 gap-2 sm:w-auto sm:min-w-80 sm:grid-cols-2">
            <StatBlock label="Rank" value={player.rank !== null ? `#${formatInt(player.rank)}` : "—"} accent />
            <StatBlock label="PP Total" value={formatPp(player.pp_total)} />
            <StatBlock label="Mapas top 10" value={formatInt(player.medals.maps_in_top10)} />
            <StatBlock
              label="Melhor posição"
              value={player.medals.best_rank !== null ? `#${formatInt(player.medals.best_rank)}` : "—"}
            />
          </div>
        </div>
      </section>

      {/* Radar + evolução */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Componentes vs. líderes</CardTitle>
          </CardHeader>
          <CardContent>
            <RadarChart player={radarPlayer} leader={leaders} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Evolução semanal</CardTitle>
          </CardHeader>
          <CardContent>
            <EvolutionChart history={player.history} />
          </CardContent>
        </Card>
      </div>

      {/* Scores */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Scores rankeados</CardTitle>
          {player.pp_total !== null ? (
            <span className="text-xs text-muted">
              Σ {formatPp(player.pp_total)} PP ponderado
            </span>
          ) : null}
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {!scores || scores.items.length === 0 ? (
            <p className="py-4 text-sm text-muted">
              Nenhum score rankeado registrado para este jogador.
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead>
                    <tr className="border-b border-border-subtle text-left text-[11px] uppercase tracking-wider text-muted">
                      <th scope="col" className="py-2.5 pr-3 font-bold">#</th>
                      <th scope="col" className="py-2.5 pr-3 font-bold">Mapa</th>
                      <th scope="col" className="hidden py-2.5 pr-3 text-right font-bold md:table-cell">Score</th>
                      <th scope="col" className="hidden py-2.5 pr-3 text-right font-bold sm:table-cell">Acc</th>
                      <th scope="col" className="py-2.5 pr-3 text-center font-bold">FC</th>
                      <th scope="col" className="py-2.5 pr-3 text-right font-bold">PP</th>
                      <th scope="col" className="hidden py-2.5 text-right font-bold lg:table-cell">Decomposição</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scores.items.map((score, index) => {
                      const position = scoresOffset + index;
                      return (
                        <tr
                          key={`${score.map_hash}-${score.difficulty}-${index}`}
                          className="border-b border-border-subtle/50 last:border-b-0"
                          style={position % 2 === 1 ? { background: "rgba(255,255,255,0.012)" } : undefined}
                        >
                          <td className="py-2.5 pr-3 font-bold tabular-nums text-muted">{position + 1}</td>
                          <td className="py-2.5 pr-3">
                            <Link
                              href={`/mapas/${score.map_hash}`}
                              className="group flex items-center gap-3 transition-colors"
                            >
                              <SmartImg
                                src={score.cover_url}
                                alt=""
                                className="h-10 w-[60px] shrink-0 rounded-md bg-surface-2 object-cover ring-1 ring-border-subtle/60 transition-transform group-hover:scale-[1.03]"
                                fallback={
                                  <span className="h-10 w-[60px] shrink-0 rounded-md bg-surface-2" />
                                }
                              />
                              <span className="min-w-0">
                                <span className="block max-w-56 truncate font-semibold transition-colors group-hover:text-secondary">
                                  {score.map_name}
                                </span>
                                <span className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                                  <Badge variant={score.difficulty === "ExpertPlus" ? "accent" : "default"}>
                                    {score.difficulty}
                                  </Badge>
                                  {score.total_stars !== null ? (
                                    <span className="tabular-nums">
                                      {formatPp(score.total_stars)}★
                                    </span>
                                  ) : null}
                                </span>
                              </span>
                            </Link>
                          </td>
                          <td className="hidden py-2.5 pr-3 text-right tabular-nums md:table-cell">
                            {formatInt(score.score)}
                          </td>
                          <td className="hidden py-2.5 pr-3 text-right tabular-nums sm:table-cell">
                            {formatAcc(score.acc)}
                          </td>
                          <td className="py-2.5 pr-3 text-center">
                            {score.full_combo ? (
                              <Badge variant="success">FC</Badge>
                            ) : (
                              <span className="text-muted/40">—</span>
                            )}
                          </td>
                          <td className="py-2.5 pr-3 text-right">
                            <span className="text-[15px] font-bold tabular-nums">
                              {formatPp(score.pp)}
                            </span>
                            <span className="mt-0.5 block text-xs font-semibold tabular-nums text-secondary">
                              {formatPp(weightedAt(score.pp ?? 0, position))} pond.
                            </span>
                          </td>
                          <td className="hidden py-2.5 text-right lg:table-cell">
                            <div className="ml-auto w-52">
                              <SubStats
                                acc={score.pp_acc}
                                tech={score.pp_tech}
                                speed={score.pp_speed}
                                size="sm"
                              />
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between text-sm text-muted">
                <span>
                  Ponderado = PP × 0,965^posição na lista ordenada por PP.
                </span>
                <span className="flex items-center gap-2">
                  {scoresPage > 1 ? (
                    <Link
                      href={buildHref(`/jogadores/${ssId}`, { page: scoresPage - 1 })}
                      className="inline-flex h-8 items-center rounded-md border border-border-subtle bg-surface px-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-2"
                    >
                      Anterior
                    </Link>
                  ) : (
                    <span className="inline-flex h-8 items-center rounded-md border border-border-subtle bg-surface px-3 text-xs font-semibold text-muted opacity-40">
                      Anterior
                    </span>
                  )}
                  <span className="tabular-nums">Página {formatInt(scores.page)}</span>
                  {scores.has_more ? (
                    <Link
                      href={buildHref(`/jogadores/${ssId}`, { page: scoresPage + 1 })}
                      className="inline-flex h-8 items-center rounded-md border border-border-subtle bg-surface px-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-2"
                    >
                      Próxima
                    </Link>
                  ) : (
                    <span className="inline-flex h-8 items-center rounded-md border border-border-subtle bg-surface px-3 text-xs font-semibold text-muted opacity-40">
                      Próxima
                    </span>
                  )}
                </span>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Calculadora */}
      <Card>
        <CardHeader>
          <CardTitle>Calculadora de PP</CardTitle>
        </CardHeader>
        <CardContent>
          <Calculator scoresPps={gainPps} />
        </CardContent>
      </Card>
    </div>
  );
}
