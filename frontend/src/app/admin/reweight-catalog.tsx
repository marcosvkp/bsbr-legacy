"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import type {
  AdminRankedMap,
  ApplyDeltaResponse,
  ReweightAnalyzeResponse,
} from "@/lib/types";
import { formatNumber } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SmartImg } from "@/components/smart-img";
import { Spinner } from "@/components/ui/spinner";

interface Props {
  token: string;
}

const PAGE_SIZE = 12;

/**
 * Reweight por mapa: catálogo paginado de TODOS os mapas rankeados com busca.
 * Ao clicar em "Simular", analisa aquele mapa (ML + performance) e permite
 * escolher direção (subir/descer) e delta antes de aplicar.
 */
export function ReweightCatalog({ token }: Props) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [maps, setMaps] = useState<AdminRankedMap[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Mapa selecionado + análise
  const [selected, setSelected] = useState<AdminRankedMap | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [data, setData] = useState<ReweightAnalyzeResponse | null>(null);
  const [deltaOverrides, setDeltaOverrides] = useState<Record<number, number>>({});
  const [directions, setDirections] = useState<Record<number, string>>({});
  const [applying, setApplying] = useState<number | null>(null);
  const [applyResult, setApplyResult] = useState<ApplyDeltaResponse | null>(null);

  const load = useCallback(
    async (q: string, pg: number) => {
      setLoading(true);
      setListError(null);
      try {
        const res = await getJson<{ items: AdminRankedMap[]; total?: number }>(
          `/admin/maps/ranked?q=${encodeURIComponent(q)}&limit=${PAGE_SIZE}&offset=${pg * PAGE_SIZE}`,
          { headers: { "X-Admin-Token": token } },
        );
        setMaps(res.items ?? []);
        setTotal(res.total ?? 0);
      } catch {
        setListError("Falha ao carregar mapas.");
      } finally {
        setLoading(false);
      }
    },
    [token],
  );

  // Busca com debounce (reseta página)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setPage(0);
      void load(query, 0);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, load]);

  useEffect(() => {
    void load(query, page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const openMap = useCallback(
    async (map: AdminRankedMap) => {
      setSelected(map);
      setAnalyzing(true);
      setAnalyzeError(null);
      setData(null);
      setApplyResult(null);
      setDeltaOverrides({});
      setDirections({});
      try {
        const res = await postJson<ReweightAnalyzeResponse>(
          "/admin/reweight/analyze",
          { map_id: map.id },
          { headers: { "X-Admin-Token": token } },
        );
        setData(res);
        const overrides: Record<number, number> = {};
        const dirs: Record<number, string> = {};
        for (const d of res.difficulties) {
          overrides[d.difficulty_id] = d.suggested_delta ?? 0;
          dirs[d.difficulty_id] = d.direction;
        }
        setDeltaOverrides(overrides);
        setDirections(dirs);
      } catch {
        setAnalyzeError("Falha ao analisar o mapa.");
      } finally {
        setAnalyzing(false);
      }
    },
    [token],
  );

  const applyDelta = useCallback(
    async (diffId: number) => {
      setApplying(diffId);
      setApplyResult(null);
      try {
        const res = await postJson<ApplyDeltaResponse>(
          "/admin/reweight/apply-delta",
          { difficulty_id: diffId, delta_stars: deltaOverrides[diffId] ?? 0 },
          { headers: { "X-Admin-Token": token } },
        );
        setApplyResult(res);
        // Reanalisa para refletir as novas estrelas
        if (selected) void openMap(selected);
      } catch {
        setApplyResult(null);
        setAnalyzeError("Falha ao aplicar.");
      } finally {
        setApplying(null);
      }
    },
    [deltaOverrides, token, selected, openMap],
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-6">
      {/* Catálogo de mapas rankeados */}
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Reweight por mapa</CardTitle>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar mapa ou mapper…"
            className="w-full max-w-sm rounded-md border border-border-subtle bg-background px-3 py-1.5 text-sm outline-none transition-colors focus:border-secondary"
          />
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {listError ? <p className="text-sm text-danger">{listError}</p> : null}
          {loading && maps.length === 0 ? (
            <div className="flex items-center justify-center gap-3 py-10 text-muted">
              <Spinner size={16} /> Carregando mapas…
            </div>
          ) : maps.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">Nenhum mapa rankeado encontrado.</p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {maps.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    onClick={() => openMap(m)}
                    className={`flex w-full items-center gap-3 rounded-lg border p-2.5 text-left transition-colors ${
                      selected?.id === m.id
                        ? "border-accent/50 bg-accent/10"
                        : "border-border-subtle bg-surface hover:border-border-subtle hover:bg-surface-2"
                    }`}
                  >
                    <SmartImg
                      src={m.cover_url ?? ""}
                      alt=""
                      fallback=""
                      className="h-11 w-11 shrink-0 rounded object-cover"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="line-clamp-1 block text-sm font-semibold" title={m.name}>
                        {m.name}
                      </span>
                      <span className="block truncate text-xs text-muted">
                        {m.mapper ?? "—"}
                        {m.bpm ? ` · ${Math.round(m.bpm)} BPM` : ""}
                      </span>
                      <span className="mt-0.5 flex flex-wrap gap-1">
                        {m.difficulties
                          .filter((d) => d.is_ranked)
                          .map((d) => (
                            <span
                              key={d.id}
                              className="rounded bg-background/80 px-1 text-[10px] font-semibold tabular-nums text-muted"
                            >
                              {d.name} {d.total_stars != null ? formatNumber(d.total_stars) : "—"}★
                            </span>
                          ))}
                      </span>
                    </span>
                    <span className="text-xs font-semibold text-secondary">Simular ›</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Paginação */}
          {total > PAGE_SIZE ? (
            <div className="flex items-center justify-between text-sm text-muted">
              <Button
                variant="ghost"
                size="sm"
                disabled={page === 0 || loading}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                ← Anterior
              </Button>
              <span className="tabular-nums">
                {total} mapas · página {page + 1}/{totalPages}
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={page + 1 >= totalPages || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Próxima →
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Análise do mapa selecionado */}
      {selected ? (
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-2">
            <CardTitle className="truncate">{selected.name}</CardTitle>
            <Badge variant="secondary">#{selected.id}</Badge>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {analyzeError ? <p className="text-sm text-danger">{analyzeError}</p> : null}
            {analyzing ? (
              <div className="flex items-center gap-3 py-6 text-muted">
                <Spinner size={16} /> Analisando com o ML + performance…
              </div>
            ) : data?.difficulties.length === 0 ? (
              <p className="text-sm text-muted">Nenhuma dificuldade rankeada neste mapa.</p>
            ) : (
              data?.difficulties.map((d) => {
                if (!d.is_ranked) return null;
                const delta = deltaOverrides[d.difficulty_id] ?? 0;
                return (
                  <div key={d.difficulty_id} className="rounded-lg border border-border-subtle bg-surface p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge>{d.name}</Badge>
                        <span className="text-xs text-muted">
                          atual:{" "}
                          <span className="font-semibold tabular-nums">
                            {d.current_stars != null ? formatNumber(d.current_stars) : "—"}★
                          </span>
                        </span>
                        {d.confidence !== "none" ? (
                          <span className="text-xs text-muted">
                            amostra {d.sample_size} · conf {d.confidence}
                          </span>
                        ) : null}
                      </div>
                    </div>

                    {/* Leitura do ML e da performance */}
                    <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
                      <span className="text-muted">
                        ML prediz:{" "}
                        <b className="tabular-nums">
                          {d.ml_stars != null ? `${formatNumber(d.ml_stars)}★` : "—"}
                        </b>
                        {d.delta_ml != null ? (
                          <span className={d.delta_ml >= 0 ? "text-success" : "text-danger"}>
                            {" "}
                            ({d.delta_ml >= 0 ? "+" : ""}
                            {formatNumber(d.delta_ml)})
                          </span>
                        ) : null}
                      </span>
                      {d.observed_acc != null ? (
                        <span className="text-muted">
                          acc observada{" "}
                          <b className="tabular-nums">{formatNumber(d.observed_acc * 100)}%</b>
                          {d.expected_acc != null ? (
                            <span className="text-muted"> vs esperada {formatNumber(d.expected_acc * 100)}%</span>
                          ) : null}
                          {d.perf_delta != null ? (
                            <span className={d.perf_delta >= 0 ? "text-success" : "text-danger"}>
                              {" "}
                              ({d.perf_delta >= 0 ? "+" : ""}
                              {formatNumber(d.perf_delta)}★)
                            </span>
                          ) : null}
                        </span>
                      ) : null}
                      {d.confidence === "none" && d.observed_acc === null ? (
                        <span className="text-warning">
                          sem amostra de jogadores — apenas predição do ML
                        </span>
                      ) : null}
                    </div>

                    {/* Direção + delta + aplicar */}
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <div className="flex items-center gap-1 rounded-md border border-border-subtle bg-background p-0.5">
                        {(["auto", "increase", "decrease"] as const).map((dir) => {
                          const labels: Record<string, string> = {
                            auto: "Auto",
                            increase: "⬆ Subir",
                            decrease: "⬇ Descer",
                          };
                          return (
                            <button
                              key={dir}
                              type="button"
                              onClick={() => {
                                setDirections((prev) => ({ ...prev, [d.difficulty_id]: dir }));
                                if (dir === "increase") {
                                  setDeltaOverrides((prev) => ({
                                    ...prev,
                                    [d.difficulty_id]: Math.max(0.05, prev[d.difficulty_id] ?? 0),
                                  }));
                                } else if (dir === "decrease") {
                                  setDeltaOverrides((prev) => ({
                                    ...prev,
                                    [d.difficulty_id]: Math.min(-0.05, prev[d.difficulty_id] ?? 0),
                                  }));
                                } else {
                                  setDeltaOverrides((prev) => ({
                                    ...prev,
                                    [d.difficulty_id]: d.suggested_delta ?? 0,
                                  }));
                                }
                              }}
                              className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
                                (directions[d.difficulty_id] ?? "auto") === dir
                                  ? "bg-accent/15 text-accent"
                                  : "text-muted hover:text-foreground"
                              }`}
                            >
                              {labels[dir]}
                            </button>
                          );
                        })}
                      </div>

                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          aria-label="Diminuir delta"
                          onClick={() =>
                            setDeltaOverrides((prev) => ({
                              ...prev,
                              [d.difficulty_id]: Math.round(((prev[d.difficulty_id] ?? 0) - 0.1) * 100) / 100,
                            }))
                          }
                          className="flex h-6 w-6 items-center justify-center rounded border border-border-subtle text-xs hover:bg-surface-2"
                        >
                          −
                        </button>
                        <input
                          type="number"
                          step="0.1"
                          value={delta}
                          onChange={(e) => {
                            const v = parseFloat(e.target.value) || 0;
                            setDeltaOverrides((prev) => ({
                              ...prev,
                              [d.difficulty_id]: Math.round(v * 100) / 100,
                            }));
                          }}
                          className="w-16 rounded border border-border-subtle bg-background px-1.5 py-0.5 text-center text-xs tabular-nums outline-none focus:border-secondary"
                          aria-label="Delta em estrelas"
                        />
                        <button
                          type="button"
                          aria-label="Aumentar delta"
                          onClick={() =>
                            setDeltaOverrides((prev) => ({
                              ...prev,
                              [d.difficulty_id]: Math.round(((prev[d.difficulty_id] ?? 0) + 0.1) * 100) / 100,
                            }))
                          }
                          className="flex h-6 w-6 items-center justify-center rounded border border-border-subtle text-xs hover:bg-surface-2"
                        >
                          +
                        </button>
                        <span className="ml-1 text-xs text-muted">
                          →{" "}
                          <b className="tabular-nums">
                            {d.current_stars != null ? formatNumber(d.current_stars + delta) : "—"}★
                          </b>
                        </span>
                      </div>

                      <Button
                        size="sm"
                        onClick={() => applyDelta(d.difficulty_id)}
                        disabled={applying !== null}
                      >
                        {applying === d.difficulty_id ? <Spinner size={12} /> : null}
                        Aplicar
                      </Button>
                    </div>
                  </div>
                );
              })
            )}

            {applyResult ? (
              <div className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm">
                Aplicado: {applyResult.old_stars}★ → {formatNumber(applyResult.new_stars)}★ ·{" "}
                {applyResult.scores_updated} scores recalculados ·{" "}
                {applyResult.players_affected} jogadores re-agregados
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
