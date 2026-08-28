import type { Metadata } from "next";
import Link from "next/link";
import { getJson } from "@/lib/api";
import type { StarsBandsResponse, StarsScope } from "@/lib/types";
import { BackendOffline, EmptyState } from "@/components/empty-state";
import { PlayerAvatar } from "@/components/player-avatar";
import { formatAcc, formatInt, formatPp } from "@/lib/format";

export const metadata: Metadata = {
  title: "Stars Ranking",
};

const SCOPES: Array<{ key: StarsScope; label: string }> = [
  { key: "br", label: "Brasil" },
  { key: "global", label: "Global" },
];

export default async function StarsRankingPage(props: PageProps<"/stars-ranking">) {
  const searchParams = await props.searchParams;
  const scopeParam = Array.isArray(searchParams.scope)
    ? searchParams.scope[0]
    : searchParams.scope;
  const scope: StarsScope = scopeParam === "global" ? "global" : "br";

  let data: StarsBandsResponse;
  try {
    data = await getJson<StarsBandsResponse>(`/stars-bands?scope=${scope}`);
  } catch {
    return <BackendOffline what="o stars ranking" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-black tracking-tight">Stars Ranking</h1>
        <p className="text-sm text-muted">
          O melhor score de cada faixa de 0,5★ entre os mapas rankeados
          {scope === "br" ? " do Brasil" : " do mundo"}.
        </p>

        <div
          role="tablist"
          aria-label="Escopo do stars ranking"
          className="flex w-fit gap-1 rounded-lg border border-border-subtle bg-surface p-1"
        >
          {SCOPES.map((tab) => {
            const active = tab.key === scope;
            return (
              <Link
                key={tab.key}
                href={`/stars-ranking?scope=${tab.key}`}
                role="tab"
                aria-selected={active}
                className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted hover:text-foreground"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>
      </div>

      {data.bands.length === 0 ? (
        <EmptyState
          title="Nenhum score encontrado"
          description="Ainda não há scores sincronizados de mapas rankeados nesse escopo."
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border-subtle">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle bg-surface text-left text-xs uppercase tracking-wider text-muted">
                <th scope="col" className="px-4 py-2.5 font-semibold">Faixa</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Melhor score</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">Acc</th>
                <th scope="col" className="hidden px-4 py-2.5 text-right font-semibold sm:table-cell">
                  Scores na faixa
                </th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">PP</th>
              </tr>
            </thead>
            <tbody>
              {data.bands.map((band) => (
                <tr
                  key={band.label}
                  className="border-b border-border-subtle/60 transition-colors last:border-b-0 hover:bg-surface/60"
                >
                  <td className="whitespace-nowrap px-4 py-2.5 font-bold tabular-nums">
                    {band.label}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-col gap-0.5">
                      <Link
                        href={`/jogadores/${band.top.player_ss_id}`}
                        className="flex w-fit items-center gap-2 rounded-md font-medium text-foreground transition-colors hover:text-secondary"
                      >
                        <PlayerAvatar name={band.top.player_name} avatarUrl={band.top.avatar_url} size={24} />
                        <span className="truncate">{band.top.player_name}</span>
                        <span className="shrink-0 rounded border border-border-subtle px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-muted">
                          {band.top.player_country}
                        </span>
                      </Link>
                      <Link
                        href={`/mapas/${band.top.map_hash}`}
                        className="w-fit max-w-xs truncate text-xs text-muted transition-colors hover:text-secondary"
                      >
                        {band.top.map_name} · {band.top.difficulty}
                      </Link>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-muted">
                    {formatAcc(band.top.acc)}
                  </td>
                  <td className="hidden px-4 py-2.5 text-right tabular-nums text-muted sm:table-cell">
                    {formatInt(band.score_count)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-bold tabular-nums">
                    {formatPp(band.top.pp)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
