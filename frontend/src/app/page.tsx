import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PlayerAvatar } from "@/components/player-avatar";
import { SmartImg } from "@/components/smart-img";
import { getJson } from "@/lib/api";
import type { MapsResponse, RankingsResponse } from "@/lib/types";
import { formatInt, formatNumber, formatPp } from "@/lib/format";

interface HealthResponse {
  status: string;
  version: string;
  environment: string;
  database: string;
  cache: string;
}

async function fetchHealth(): Promise<
  { online: true; data: HealthResponse } | { online: false }
> {
  try {
    const data = await getJson<HealthResponse>("/health");
    return { online: true, data };
  } catch {
    return { online: false };
  }
}

async function fetchHomeData(): Promise<{
  top: RankingsResponse | null;
  recentMaps: MapsResponse | null;
}> {
  const [top, recentMaps] = await Promise.all([
    getJson<RankingsResponse>("/rankings?component=total&page=1&page_size=5&country=BR").catch(
      () => null,
    ),
    getJson<MapsResponse>("/maps?sort=recent&page=1&page_size=5").catch(() => null),
  ]);
  return { top, recentMaps };
}

export default async function HomePage() {
  const [health, { top, recentMaps }] = await Promise.all([fetchHealth(), fetchHomeData()]);

  return (
    <div className="flex flex-col gap-10">
      <section className="flex flex-col items-center gap-4 py-14 text-center">
        <Badge variant="accent" className="fade-up uppercase tracking-widest glow-accent">
          Temporada 2.0
        </Badge>
        <h1 className="fade-up font-display text-4xl font-extrabold uppercase tracking-tight sm:text-6xl"
          style={{ animationDelay: "80ms" }}>
          BSBR — <span className="text-glow-accent text-accent">Beat Saber Brasil</span>{" "}
          <span className="text-glow-secondary text-secondary">Ranking</span>
        </h1>
        <p
          className="fade-up max-w-xl text-muted"
          style={{ animationDelay: "160ms" }}
        >
          O ranking oficial da comunidade brasileira de Beat Saber: jogadores,
          mapas rankeados e pontuações atualizadas.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Status da API</CardTitle>
            <CardDescription>GET /health do backend BSBR</CardDescription>
          </CardHeader>
          <CardContent>
            {health.online ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="success">ONLINE</Badge>
                <span className="text-sm text-muted">
                  status {health.data.status} · v{health.data.version} · env{" "}
                  {health.data.environment} · db {health.data.database} · cache{" "}
                  {health.data.cache}
                </span>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="danger">OFFLINE</Badge>
                <span className="text-sm text-muted">
                  Backend indisponível. Suba a API para ver o status em tempo
                  real.
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sobre o ranking</CardTitle>
            <CardDescription>Como funciona</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm text-muted">
            <p>
              Jogadores ganham pontos ao completar mapas rankeados. O placar é
              recalculado pelos workers do backend e publicado aqui.
            </p>
            <div className="flex gap-2">
              <Link
                href="/ranking"
                className="inline-flex h-8 items-center rounded-md bg-accent px-3 text-xs font-semibold text-white transition-colors hover:bg-accent-strong"
              >
                Ver ranking
              </Link>
              <Link
                href="/mapas"
                className="inline-flex h-8 items-center rounded-md border border-border-subtle bg-surface px-3 text-xs font-semibold transition-colors hover:bg-surface-2"
              >
                Explorar mapas
              </Link>
            </div>
          </CardContent>
        </Card>
      </section>

      <section aria-label="Prévia do ranking" className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top jogadores</CardTitle>
            <CardDescription>Melhores do ranking geral</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {top === null ? (
              <p className="py-2 text-muted">Backend indisponível — sem dados agora.</p>
            ) : top.items.length === 0 ? (
              <p className="py-2 text-muted">Nenhum jogador rankeado ainda.</p>
            ) : (
              top.items.map((player) => (
                <Link
                  key={player.ss_id}
                  href={`/jogadores/${player.ss_id}`}
                  className="group flex items-center justify-between gap-3 rounded-md bg-background px-3 py-2 transition-colors hover:bg-surface-2"
                >
                  <span className="flex min-w-0 items-center gap-2.5">
                    <span className="w-7 shrink-0 text-xs font-bold tabular-nums text-muted">
                      #{formatInt(player.rank)}
                    </span>
                    <PlayerAvatar name={player.name} avatarUrl={player.avatar_url} size={28} />
                    <span className="truncate font-semibold text-foreground transition-colors group-hover:text-secondary">
                      {player.name}
                    </span>
                  </span>
                  <span className="shrink-0 tabular-nums text-muted">{formatPp(player.pp_total)} PP</span>
                </Link>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Rankeados recentemente</CardTitle>
            <CardDescription>Mapas adicionados ao catálogo</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {recentMaps === null ? (
              <p className="py-2 text-muted">Backend indisponível — sem dados agora.</p>
            ) : recentMaps.items.length === 0 ? (
              <p className="py-2 text-muted">Nenhum mapa no catálogo ainda.</p>
            ) : (
              recentMaps.items.map((map) => (
                <Link
                  key={map.hash}
                  href={`/mapas/${map.hash}`}
                  className="group flex items-center justify-between gap-3 rounded-md bg-background px-3 py-2 transition-colors hover:bg-surface-2"
                >
                  <span className="flex min-w-0 items-center gap-2.5">
                    <SmartImg
                      src={map.cover_url}
                      alt=""
                      className="h-7 w-11 shrink-0 rounded bg-surface-2 object-cover"
                      fallback={<span className="h-7 w-11 shrink-0 rounded bg-surface-2" />}
                    />
                    <span className="truncate font-semibold text-foreground transition-colors group-hover:text-secondary">
                      {map.name}
                    </span>
                  </span>
                  <span className="shrink-0 tabular-nums text-muted">
                    {map.difficulties[0]?.total_stars != null
                      ? `${formatNumber(map.difficulties[0].total_stars)}★`
                      : "—"}
                  </span>
                </Link>
              ))
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
