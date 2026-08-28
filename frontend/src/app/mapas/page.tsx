import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { SmartImg } from "@/components/smart-img";
import { getJson } from "@/lib/api";
import type { MapSummary, MapsResponse } from "@/lib/types";
import { formatInt, formatNumber } from "@/lib/format";
import { BackendOffline, EmptyState } from "@/components/empty-state";
import { Pagination } from "@/components/pagination";
import { SubStats } from "@/components/sub-stats";
import { SortSelect } from "./sort-select";

export const metadata: Metadata = {
  title: "Mapas",
};

const PAGE_SIZE = 24;
const SORTS: Record<string, true> = { stars: true, recent: true, name: true };

function parseSort(value: string | undefined): string {
  return value !== undefined && SORTS[value] ? value : "stars";
}

function parsePage(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
}

function StarIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="h-3.5 w-3.5 text-warning"
    >
      <path d="M10 1.7l2.47 5 5.53.8-4 3.9.94 5.5L10 14.3l-4.94 2.6L6 11.4l-4-3.9 5.53-.8 2.47-5Z" />
    </svg>
  );
}

function Cover({ map }: { map: MapSummary }) {
  return (
    <SmartImg
      src={map.cover_url}
      alt={`Capa de ${map.name}`}
      className="aspect-[16/9] w-full bg-surface-2 object-cover transition-transform duration-500 group-hover:scale-[1.06]"
      fallback={
        <div className="flex aspect-[16/9] w-full items-center justify-center bg-surface-2 text-muted/40">
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="h-10 w-10"
          >
            <circle cx="7" cy="17" r="3" />
            <circle cx="18" cy="15" r="3" />
            <path d="M10 17V6l11-2v11" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      }
    />
  );
}

interface MapCardProps {
  map: MapSummary;
}

function MapCard({ map }: MapCardProps) {
  const main = map.difficulties[0];
  const styleTags = main?.style_tags ?? [];
  const visibleTags = styleTags.slice(0, 3);
  const hiddenTags = Math.max(styleTags.length - 3, 0);

  return (
    <Link
      href={`/mapas/${map.hash}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-secondary/50 hover:shadow-[0_8px_30px_-8px_rgba(59,130,246,0.25)]"
    >
      <div className="relative overflow-hidden">
        <Cover map={map} />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-gradient-to-t from-surface via-surface/10 to-transparent"
        />
        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 p-3">
          <span className="flex items-center gap-1 rounded-md border border-warning/30 bg-background/70 px-2 py-1 text-sm font-black tabular-nums text-warning backdrop-blur-sm">
            <StarIcon />
            {main?.total_stars != null ? formatNumber(main.total_stars) : "—"}
          </span>
          {map.bpm != null ? (
            <span className="rounded-md border border-border-subtle bg-background/70 px-2 py-1 text-[11px] font-bold tabular-nums text-muted backdrop-blur-sm">
              {formatInt(map.bpm)} BPM
            </span>
          ) : null}
        </div>
        {main ? (
          <span className="absolute right-3 top-3 rounded-md bg-accent px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-white shadow-[0_0_12px_var(--glow-accent)]">
            {main.name}
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col gap-2.5 p-3.5">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-1 text-[15px] font-bold tracking-tight text-foreground transition-colors group-hover:text-secondary">
            {map.name}
          </h3>
        </div>
        <p className="truncate text-xs text-muted">
          {map.mapper}
          <span className="mx-1.5 text-muted/50">·</span>
          <span className="italic">{map.song_author}</span>
        </p>
        {visibleTags.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {visibleTags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-secondary/20 bg-secondary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-secondary"
              >
                {tag}
              </span>
            ))}
            {hiddenTags > 0 ? (
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-semibold text-muted">
                +{hiddenTags}
              </span>
            ) : null}
          </div>
        ) : null}
        {main ? (
          <div className="mt-auto pt-1.5">
            <SubStats
              acc={main.acc_stars}
              tech={main.tech_stars}
              speed={main.speed_stars}
              format={(v) => (v != null ? formatNumber(v) : "—")}
              size="sm"
            />
          </div>
        ) : null}
      </div>
    </Link>
  );
}

export default async function MapsPage(props: PageProps<"/mapas">) {
  const searchParams = await props.searchParams;
  const sort = parseSort(
    Array.isArray(searchParams.sort) ? searchParams.sort[0] : searchParams.sort,
  );
  const page = parsePage(Array.isArray(searchParams.page) ? searchParams.page[0] : searchParams.page);

  let data: MapsResponse;
  try {
    data = await getJson<MapsResponse>(`/maps?sort=${sort}&page=${page}&page_size=${PAGE_SIZE}`);
  } catch {
    return <BackendOffline what="os mapas rankeados" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-extrabold uppercase tracking-tight">
            Mapas <span className="text-secondary">rankeados</span>
          </h1>
          <p className="mt-1 text-sm text-muted">
            {formatInt(data.total)} mapas no catálogo brasileiro
          </p>
        </div>
        <Suspense fallback={null}>
          <SortSelect value={sort} />
        </Suspense>
      </div>

      {data.items.length === 0 ? (
        <EmptyState
          title={page > 1 ? "Sem mapas nesta página" : "Nenhum mapa rankeado"}
          description={
            page > 1
              ? undefined
              : "O catálogo é populado pelo batch semanal a partir dos leaderboards."
          }
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data.items.map((map) => (
              <MapCard key={map.hash} map={map} />
            ))}
          </div>
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            basePath="/mapas"
            params={{ sort }}
          />
        </>
      )}
    </div>
  );
}
