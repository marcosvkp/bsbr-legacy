import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { SmartImg } from "@/components/smart-img";
import { getJson } from "@/lib/api";
import type { MapSummary, MapsResponse, QualificationResponse } from "@/lib/types";
import { formatInt, formatNumber } from "@/lib/format";
import { BackendOffline, EmptyState } from "@/components/empty-state";
import { Pagination } from "@/components/pagination";
import { SubStats } from "@/components/sub-stats";
import { PlaylistDownload } from "@/components/playlist-download";
import { SuggestMap } from "@/components/suggest-map";
import { MapsFilter } from "./maps-filter";
import { SortSelect } from "./sort-select";

export const metadata: Metadata = {
  title: "Mapas",
};

const PAGE_SIZE = 24;
const SORTS: Record<string, true> = { stars: true, recent: true, name: true };
const QUALIFICATION_TAB = "qualification";

function parseSort(value: string | undefined): string {
  return value !== undefined && SORTS[value] ? value : "stars";
}

function parsePage(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
}

function parseQuery(value: string | undefined): string {
  return value ?? "";
}

function parseStars(value: string | undefined): number {
  const parsed = Number.parseFloat(value ?? "0");
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
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
      </div>
      <div className="flex flex-1 flex-col gap-2.5 p-3.5">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-2 text-[15px] font-bold leading-snug tracking-tight text-foreground transition-colors group-hover:text-secondary">
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

const STATUS_LABEL: Record<string, { label: string; badge: string }> = {
  candidate: { label: "Sugerido", badge: "border-warning/40 bg-warning/10 text-warning" },
  qualified: { label: "Qualificado", badge: "border-secondary/40 bg-secondary/10 text-secondary" },
};

function QualificationList({ data }: { data: QualificationResponse }) {
  if (data.items.length === 0) {
    return (
      <EmptyState
        title="Nenhum mapa em qualificação"
        description="Os mapas sugeridos pela comunidade e analisados pelo ML aparecem aqui."
      />
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {data.items.map((item) => {
        const status = STATUS_LABEL[item.status] ?? STATUS_LABEL.candidate;
        const mainDiff = item.difficulties[0];
        return (
          <div
            key={item.id}
            className="flex flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm"
          >
            <div className="relative overflow-hidden">
              <SmartImg
                src={item.cover_url}
                alt={`Capa de ${item.name}`}
                className="aspect-[16/9] w-full bg-surface-2 object-cover"
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
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-gradient-to-t from-surface via-surface/10 to-transparent"
              />
              <span
                className={`absolute right-3 top-3 rounded-md border px-2 py-0.5 text-[10px] font-black uppercase tracking-widest backdrop-blur-sm ${status.badge}`}
              >
                {status.label}
              </span>
            </div>
            <div className="flex flex-1 flex-col gap-1.5 p-3.5">
              <h3 className="line-clamp-2 text-[15px] font-bold leading-snug tracking-tight text-foreground">
                {item.name}
              </h3>
              <p className="truncate text-xs text-muted">
                {item.mapper ?? "Mapper desconhecido"}
                {item.bpm != null ? (
                  <>
                    <span className="mx-1.5 text-muted/50">·</span>
                    {formatInt(item.bpm)} BPM
                  </>
                ) : null}
              </p>
              <div className="mt-auto flex flex-wrap gap-1 pt-1.5">
                {item.difficulties.slice(0, 3).map((d) => (
                  <span
                    key={d.name}
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                      d.is_ranked === false
                        ? "border-border-subtle bg-background/60 text-muted/60 line-through"
                        : "border-border-subtle bg-surface-2 text-muted"
                    }`}
                  >
                    {d.name}
                    {d.total_stars != null ? ` · ${formatNumber(d.total_stars)}★` : ""}
                    {d.is_ranked === false ? " (fora)" : ""}
                  </span>
                ))}
                {item.difficulties.length > 3 ? (
                  <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-semibold text-muted">
                    +{item.difficulties.length - 3}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default async function MapsPage(props: PageProps<"/mapas">) {
  const searchParams = await props.searchParams;
  const tab = Array.isArray(searchParams.tab) ? searchParams.tab[0] : searchParams.tab;
  const isQualification = tab === QUALIFICATION_TAB;
  const sort = parseSort(
    Array.isArray(searchParams.sort) ? searchParams.sort[0] : searchParams.sort,
  );
  const page = parsePage(Array.isArray(searchParams.page) ? searchParams.page[0] : searchParams.page);
  const q = parseQuery(Array.isArray(searchParams.q) ? searchParams.q[0] : searchParams.q);
  const minStars = parseStars(
    Array.isArray(searchParams.min_stars) ? searchParams.min_stars[0] : searchParams.min_stars,
  );

  let data: MapsResponse | null = null;
  let qualification: QualificationResponse | null = null;
  let offline = false;
  try {
    if (isQualification) {
      qualification = await getJson<QualificationResponse>("/maps/qualification");
    } else {
      const params = new URLSearchParams({ sort, page: String(page), page_size: String(PAGE_SIZE) });
      if (q) params.set("q", q);
      if (minStars > 0) params.set("min_stars", String(minStars));
      data = await getJson<MapsResponse>(`/maps?${params.toString()}`);
    }
  } catch {
    offline = true;
  }

  const tabs = (
    <div role="tablist" aria-label="Catálogo de mapas" className="flex w-fit gap-1 rounded-lg border border-border-subtle bg-surface p-1">
      <Link
        role="tab"
        aria-selected={!isQualification}
        href="/mapas"
        className={`rounded-md px-4 py-1.5 text-sm font-bold transition-colors ${
          !isQualification
            ? "bg-secondary text-white shadow-[0_0_12px_var(--glow-secondary)]"
            : "text-muted hover:text-foreground"
        }`}
      >
        Rankeados
      </Link>
      <Link
        role="tab"
        aria-selected={isQualification}
        href="/mapas?tab=qualification"
        className={`rounded-md px-4 py-1.5 text-sm font-bold transition-colors ${
          isQualification
            ? "bg-secondary text-white shadow-[0_0_12px_var(--glow-secondary)]"
            : "text-muted hover:text-foreground"
        }`}
      >
        Qualificação
      </Link>
    </div>
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-extrabold uppercase tracking-tight">
            Mapas <span className="text-secondary">{isQualification ? "em qualificação" : "rankeados"}</span>
          </h1>
          <p className="mt-1 text-sm text-muted">
            {isQualification
              ? "Sugeridos pela comunidade e analisados pelo ML — aguardando staff"
              : `${formatInt(data?.total ?? 0)} mapas no catálogo brasileiro`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {!isQualification ? <SuggestMap /> : null}
          {!isQualification && data ? <PlaylistDownload total={data.total} /> : null}
        </div>
      </div>

      {!isQualification ? (
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <Suspense fallback={null}>
            <MapsFilter initialQuery={q} minStars={minStars} />
          </Suspense>
          <Suspense fallback={null}>
            <SortSelect value={sort} />
          </Suspense>
        </div>
      ) : null}

      {tabs}

      {offline ? (
        <BackendOffline what={isQualification ? "a fila de qualificação" : "os mapas rankeados"} />
      ) : isQualification ? (
        <QualificationList data={qualification!} />
      ) : data!.items.length === 0 ? (
        <EmptyState
          title={q || minStars > 0 ? "Nenhum mapa encontrado" : page > 1 ? "Sem mapas nesta página" : "Nenhum mapa rankeado"}
          description={
            q || minStars > 0
              ? "Ajuste a busca ou o filtro de estrelas para encontrar o que procura."
              : page > 1
                ? undefined
                : "O catálogo é populado pelo batch semanal a partir dos leaderboards."
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data!.items.map((map) => (
              <MapCard key={map.hash} map={map} />
            ))}
          </div>
          <Pagination
            page={data!.page}
            pageSize={data!.page_size}
            total={data!.total}
            basePath="/mapas"
            params={{ sort, q: q || undefined, min_stars: minStars > 0 ? String(minStars) : undefined }}
          />
        </>
      )}
    </div>
  );
}
