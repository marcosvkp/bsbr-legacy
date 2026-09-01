import type { Metadata } from "next";
import Link from "next/link";
import { ApiError, getJson } from "@/lib/api";
import type { MapDetail } from "@/lib/types";
import { formatDate, formatInt } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SmartImg } from "@/components/smart-img";
import { BackendOffline, EmptyState } from "@/components/empty-state";
import { MapActions } from "./map-actions";
import { MapViewer } from "./map-viewer";

export async function generateMetadata(
  props: PageProps<"/mapas/[hash]">,
): Promise<Metadata> {
  const { hash } = await props.params;
  const title = `Mapa ${hash.slice(0, 8)} · BSBR`;
  return {
    title,
    openGraph: {
      title,
      description: "Mapa rankeado no ranking brasileiro de Beat Saber",
      type: "website",
      images: [{ url: `/api/v1/og/maps/${hash}.png`, width: 1200, height: 630, alt: title }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: "Mapa rankeado no ranking brasileiro de Beat Saber",
      images: [`/api/v1/og/maps/${hash}.png`],
    },
  };
}

async function loadMap(hash: string): Promise<{ ok: true; map: MapDetail } | { ok: false; status: number | null }> {
  try {
    const map = await getJson<MapDetail>(`/maps/${encodeURIComponent(hash)}`);
    return { ok: true, map };
  } catch (cause) {
    return { ok: false, status: cause instanceof ApiError ? cause.status : null };
  }
}

export default async function MapDetailPage(props: PageProps<"/mapas/[hash]">) {
  const { hash } = await props.params;
  const result = await loadMap(hash);

  if (!result.ok) {
    if (result.status === 404) {
      return (
        <EmptyState
          title="Mapa não encontrado"
          description={`Nenhum mapa rankeado com o hash ${hash}.`}
        />
      );
    }
    return <BackendOffline what="os dados do mapa" />;
  }

  const map = result.map;

  return (
    <div className="flex flex-col gap-6">
      {/* Cabeçalho */}
      <section className="relative overflow-hidden rounded-xl border border-border-subtle bg-surface">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 60% 130% at 10% -20%, rgba(239,68,68,0.14), transparent 60%)," +
              "radial-gradient(ellipse 50% 120% at 95% 120%, rgba(59,130,246,0.12), transparent 60%)",
          }}
        />
        <div className="relative flex flex-col gap-5 p-5 sm:flex-row">
          <div className="w-full shrink-0 overflow-hidden rounded-lg border border-border-subtle sm:w-72">
            <SmartImg
              src={map.cover_url}
              alt={`Capa de ${map.name}`}
              className="aspect-[16/9] w-full bg-surface-2 object-cover"
              fallback={<div className="aspect-[16/9] w-full bg-surface-2" />}
            />
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted">
                <Link href="/mapas" className="transition-colors hover:text-secondary">
                  Mapas
                </Link>
                <span className="mx-1.5 text-muted/40">/</span>
                <span className="font-mono normal-case tracking-normal">{map.hash.slice(0, 12)}…</span>
              </p>
              <MapActions beatsaverId={map.beatsaver_id} hash={map.hash} />
            </div>
            <h1 className="font-display text-3xl font-extrabold uppercase leading-tight tracking-tight">
              {map.name}
            </h1>
            <p className="text-sm text-muted">
              <span className="font-semibold text-foreground">{map.mapper}</span>
              <span className="mx-1.5 text-muted/50">·</span>
              <span className="italic">{map.song_author}</span>
              {map.bpm != null ? (
                <>
                  <span className="mx-1.5 text-muted/50">·</span>
                  {formatInt(map.bpm)} BPM
                </>
              ) : null}
            </p>
            {(map.tags ?? []).length > 0 ? (
              <div className="mt-1 flex flex-wrap gap-1.5">
                {(map.tags ?? []).map((tag) => (
                  <Badge key={tag}>{tag}</Badge>
                ))}
              </div>
            ) : null}
            {map.difficulties_detail.length > 0 && map.difficulties_detail[0].ranked_at ? (
              <p className="mt-auto pt-2 text-xs text-muted">
                Rankeado em {formatDate(map.difficulties_detail[0].ranked_at)}
              </p>
            ) : null}
          </div>
        </div>
      </section>

      {/* Dificuldade selecionada + leaderboard + histórico */}
      <Card>
        <CardHeader>
          <CardTitle>Dificuldades</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <MapViewer map={map} />
        </CardContent>
      </Card>
    </div>
  );
}
