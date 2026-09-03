"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, deleteJson, getJson, postJson } from "@/lib/api";
import type {
  AdminRankedMap,
  ReweightAnalyzeDifficulty,
  ReweightAnalyzeResponse,
  ReweightEnqueueResponse,
  ReweightMethod,
  ReweightPreviewResponse,
} from "@/lib/types";
import { formatNumber } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SmartImg } from "@/components/smart-img";
import { Spinner } from "@/components/ui/spinner";

const PAGE_SIZE = 12;

const METHOD_OPTIONS: Array<{ value: ReweightMethod; label: string }> = [
  { value: "ml", label: "Só ML" },
  { value: "perf", label: "Só perf" },
  { value: "mix", label: "50-50" },
];

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

/** Delta combinado do método — mesma regra do backend `_delta_by_method`. */
function deltaByMethod(
  d: ReweightAnalyzeDifficulty,
  method: ReweightMethod,
): number | null {
  const ml = d.delta_ml;
  const perf = d.perf_delta;
  if (method === "ml") return ml;
  if (method === "perf") return perf;
  if (ml !== null && perf !== null) return round2(0.5 * ml + 0.5 * perf);
  return ml ?? perf;
}

/** "+0,40★" / "-0,10★" / "—". */
function signedStars(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatNumber(value)}★`;
}

/**
 * Reweight por mapa: catálogo paginado de TODOS os mapas rankeados com busca.
 * Ao clicar em "Simular", analisa o mapa (ML + performance) e permite escolher
 * o peso do método (só ML / só perf / 50-50), conferir o preview com ruído
 * seedado e ENFILEIRAR o ajuste para o próximo batch semanal.
 */
export function ReweightCatalog() {
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

  // Método escolhido por dificuldade (default "mix")
  const [methods, setMethods] = useState<Record<number, ReweightMethod>>({});
  // Preview com ruído seedado por dificuldade
  const [seeds, setSeeds] = useState<Record<number, string>>({});
  const [previews, setPreviews] = useState<Record<number, ReweightPreviewResponse | null>>({});
  const [previewing, setPreviewing] = useState<Record<number, boolean>>({});

  // Ações de fila
  const [actingId, setActingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const load = useCallback(async (q: string, pg: number) => {
    setLoading(true);
    setListError(null);
    try {
      const res = await getJson<{ items: AdminRankedMap[]; total?: number }>(
        `/admin/maps/ranked?q=${encodeURIComponent(q)}&limit=${PAGE_SIZE}&offset=${pg * PAGE_SIZE}`,
      );
      setMaps(res.items ?? []);
      setTotal(res.total ?? 0);
    } catch {
      setListError("Falha ao carregar mapas.");
    } finally {
      setLoading(false);
    }
  }, []);

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

  /** Busca a análise do mapa (reflete a fila manual atual no queued_delta). */
  const fetchAnalysis = useCallback(async (mapId: number) => {
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const res = await postJson<ReweightAnalyzeResponse>("/admin/reweight/analyze", {
        map_id: mapId,
      });
      setData(res);
    } catch (cause) {
      setData(null);
      setAnalyzeError(cause instanceof ApiError ? cause.message : "Falha ao analisar o mapa.");
    } finally {
      setAnalyzing(false);
    }
  }, []);

  const openMap = useCallback(
    (map: AdminRankedMap) => {
      setSelected(map);
      setData(null);
      setMethods({});
      setSeeds({});
      setPreviews({});
      setActionError(null);
      setActionNotice(null);
      void fetchAnalysis(map.id);
    },
    [fetchAnalysis],
  );

  const enqueue = useCallback(
    async (d: ReweightAnalyzeDifficulty) => {
      const method = methods[d.difficulty_id] ?? "mix";
      setActingId(d.difficulty_id);
      setActionError(null);
      setActionNotice(null);
      try {
        await postJson<ReweightEnqueueResponse>("/admin/reweight/enqueue", {
          difficulty_id: d.difficulty_id,
          method,
        });
        setActionNotice(
          `Dificuldade ${d.name} enfileirada (método ${
            method === "mix" ? "50-50" : method === "ml" ? "só ML" : "só perf"
          }) — entra no próximo batch semanal.`,
        );
        if (selected) void fetchAnalysis(selected.id);
      } catch (cause) {
        setActionError(cause instanceof ApiError ? cause.message : "Falha ao enfileirar.");
      } finally {
        setActingId(null);
      }
    },
    [methods, selected, fetchAnalysis],
  );

  const removeFromQueue = useCallback(
    async (d: ReweightAnalyzeDifficulty) => {
      setActingId(d.difficulty_id);
      setActionError(null);
      setActionNotice(null);
      try {
        await deleteJson(`/admin/reweight/enqueue/${d.difficulty_id}`);
        setActionNotice(`Dificuldade ${d.name} removida da fila manual.`);
        if (selected) void fetchAnalysis(selected.id);
      } catch (cause) {
        setActionError(cause instanceof ApiError ? cause.message : "Falha ao remover da fila.");
      } finally {
        setActingId(null);
      }
    },
    [selected, fetchAnalysis],
  );

  const runPreview = useCallback(
    async (d: ReweightAnalyzeDifficulty) => {
      const raw = (seeds[d.difficulty_id] ?? "").trim();
      const seed = Number.parseInt(raw, 10);
      if (!raw || !Number.isFinite(seed)) {
        setActionError("Informe um seed numérico inteiro para o preview com ruído.");
        return;
      }
      const method = methods[d.difficulty_id] ?? "mix";
      setPreviewing((prev) => ({ ...prev, [d.difficulty_id]: true }));
      setActionError(null);
      try {
        const res = await postJson<ReweightPreviewResponse>(
          "/admin/reweight/preview-difficulty",
          {
            difficulty_id: d.difficulty_id,
            method,
            seed,
            noise_sigma: 0.47,
          },
        );
        setPreviews((prev) => ({ ...prev, [d.difficulty_id]: res }));
      } catch (cause) {
        setActionError(cause instanceof ApiError ? cause.message : "Falha ao gerar o preview.");
      } finally {
        setPreviewing((prev) => ({ ...prev, [d.difficulty_id]: false }));
      }
    },
    [methods, seeds],
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
            {actionError ? (
              <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                {actionError}
              </p>
            ) : null}
            {actionNotice ? (
              <p role="status" className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm">
                {actionNotice}
              </p>
            ) : null}
            {analyzeError ? <p role="alert" className="text-sm text-danger">{analyzeError}</p> : null}
            {analyzing && !data ? (
              <div className="flex items-center gap-3 py-6 text-muted">
                <Spinner size={16} /> Analisando com o ML + performance…
              </div>
            ) : data?.difficulties.length === 0 ? (
              <p className="text-sm text-muted">Nenhuma dificuldade rankeada neste mapa.</p>
            ) : (
              data?.difficulties.map((d) => {
                if (!d.is_ranked) return null;
                const method = methods[d.difficulty_id] ?? "mix";
                const delta = deltaByMethod(d, method);
                const queued = d.queued_delta;
                const preview = previews[d.difficulty_id] ?? null;
                const busy = actingId === d.difficulty_id;
                const previewBusy = previewing[d.difficulty_id] ?? false;
                return (
                  <div key={d.difficulty_id} className="rounded-lg border border-border-subtle bg-surface p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
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
                        {queued !== null ? (
                          <Badge variant="success">na fila (Δ{signedStars(queued)})</Badge>
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
                            ({signedStars(d.delta_ml)})
                          </span>
                        ) : null}
                      </span>
                      {d.observed_acc != null ? (
                        <span className="text-muted">
                          acc observada{" "}
                          <b className="tabular-nums">{formatNumber(d.observed_acc * 100)}%</b>
                          {d.expected_acc != null ? (
                            <span className="text-muted">
                              {" "}vs esperada {formatNumber(d.expected_acc * 100)}%
                            </span>
                          ) : null}
                          {d.perf_delta != null ? (
                            <span className={d.perf_delta >= 0 ? "text-success" : "text-danger"}>
                              {" "}
                              ({signedStars(d.perf_delta)})
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

                    {/* Método (peso ML/perf) + delta resultante */}
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <div className="flex items-center gap-1 rounded-md border border-border-subtle bg-background p-0.5">
                        {METHOD_OPTIONS.map((opt) => (
                          <button
                            key={opt.value}
                            type="button"
                            aria-pressed={method === opt.value}
                            onClick={() =>
                              setMethods((prev) => ({ ...prev, [d.difficulty_id]: opt.value }))
                            }
                            className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
                              method === opt.value
                                ? "bg-accent/15 text-accent"
                                : "text-muted hover:text-foreground"
                            }`}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                      <span className="text-xs text-muted">
                        Δ {signedStars(delta)}
                        {delta !== null && d.current_stars != null ? (
                          <>
                            {" "}→{" "}
                            <b className="tabular-nums text-foreground">
                              {formatNumber(d.current_stars + delta)}★
                            </b>
                          </>
                        ) : null}
                        {delta === null ? (
                          <span className="text-warning"> sem ML nem perf para estimar</span>
                        ) : null}
                      </span>
                    </div>

                    {/* Enfileirar / remover da fila */}
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      {queued !== null ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => removeFromQueue(d)}
                          disabled={actingId !== null}
                          className="text-danger hover:text-danger"
                        >
                          {busy ? <Spinner size={12} /> : null}
                          Remover da fila
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => enqueue(d)}
                          disabled={actingId !== null || delta === null}
                          title={
                            delta === null
                              ? "Sem predição do ML nem amostra de performance para enfileirar."
                              : undefined
                          }
                        >
                          {busy ? <Spinner size={12} /> : null}
                          Enfileirar
                        </Button>
                      )}
                      <span className="text-xs text-muted">
                        O reweight entra no próximo batch semanal.
                      </span>
                    </div>

                    {/* Preview com ruído seedado */}
                    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md bg-background/60 px-2 py-1.5 text-xs">
                      <label className="flex items-center gap-1.5 text-muted">
                        seed
                        <input
                          type="text"
                          inputMode="numeric"
                          value={seeds[d.difficulty_id] ?? ""}
                          onChange={(e) =>
                            setSeeds((prev) => ({ ...prev, [d.difficulty_id]: e.target.value }))
                          }
                          placeholder="42"
                          aria-label={`Seed do preview de ${d.name}`}
                          className="w-16 rounded border border-border-subtle bg-background px-1.5 py-0.5 text-center font-mono tabular-nums outline-none focus:border-secondary"
                        />
                      </label>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => runPreview(d)}
                        disabled={previewBusy}
                      >
                        {previewBusy ? <Spinner size={12} /> : null}
                        Preview (ruído)
                      </Button>
                      {preview ? (
                        <span className="text-muted">
                          delta base {signedStars(preview.delta_base)} →{" "}
                          <b className="tabular-nums">{formatNumber(preview.stars_base)}★</b>
                          {preview.stars_p5 != null && preview.stars_p95 != null ? (
                            <>
                              {" "}
                              <span className="text-muted">
                                · intervalo provável (seed {preview.seed}): ★{" "}
                                {formatNumber(preview.stars_p5)} … {formatNumber(preview.stars_p95)}
                                {preview.stars_p50 != null ? (
                                  <span> · mediana {formatNumber(preview.stars_p50)}</span>
                                ) : null}
                              </span>
                            </>
                          ) : null}
                        </span>
                      ) : null}
                    </div>
                  </div>
                );
              })
            )}

            <p className="text-xs text-muted">
              As mudanças entram no próximo batch semanal — nada é aplicado em tempo real pelo catálogo.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
