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
import { Spinner } from "@/components/ui/spinner";

interface Props {
  token: string;
  /** Callback externo para recarregar a lista de sugestões pendentes após aplicar. */
  onApplied?: () => void;
}

/**
 * Card "Análise manual de reweight" — busca mapas rankeados ou cola BeatSaver ID,
 * analisa com ML, mostra resultado por dificuldade com direção e delta ajustável.
 */
export function ReweightAnalyze({ token, onApplied }: Props) {
  const [input, setInput] = useState("");
  const [searchResults, setSearchResults] = useState<AdminRankedMap[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedMapId, setSelectedMapId] = useState<number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ReweightAnalyzeResponse | null>(null);

  // Delta override por dificuldade (chave = difficulty_id)
  const [deltaOverrides, setDeltaOverrides] = useState<Record<number, number>>({});
  const [directions, setDirections] = useState<Record<number, string>>({});
  // Estado de apply por dificuldade
  const [applying, setApplying] = useState<number | null>(null);
  const [applyResult, setApplyResult] = useState<ApplyDeltaResponse | null>(null);

  // Busca autocomplete
  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim() || q.length < 2) {
        setSearchResults([]);
        setSearchOpen(false);
        return;
      }
      try {
        const res = await getJson<{ items: AdminRankedMap[] }>(
          `/admin/maps/ranked?q=${encodeURIComponent(q)}&limit=8`,
          { headers: { "X-Admin-Token": token } },
        );
        setSearchResults(res.items ?? []);
        setSearchOpen(res.items?.length > 0);
      } catch {
        setSearchResults([]);
      }
    },
    [token],
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(input), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [input, doSearch]);

  // Fecha busca ao clicar fora
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const selectMap = (map: AdminRankedMap) => {
    setInput(map.name);
    setSelectedMapId(map.id);
    setSearchOpen(false);
    setData(null);
    setApplyResult(null);
  };

  const runAnalyze = useCallback(async () => {
    const source = input.trim();
    if (!source) return;
    setLoading(true);
    setError(null);
    setData(null);
    setApplyResult(null);
    setDeltaOverrides({});
    setDirections({});
    try {
      const body = selectedMapId ? { map_id: selectedMapId } : { source };
      const res = await postJson<ReweightAnalyzeResponse>(
        "/admin/reweight/analyze",
        body,
        { headers: { "X-Admin-Token": token } },
      );
      setData(res);
      // Inicializa overrides com o delta sugerido
      const overrides: Record<number, number> = {};
      const dirs: Record<number, string> = {};
      for (const d of res.difficulties) {
        overrides[d.difficulty_id] = d.suggested_delta ?? 0;
        dirs[d.difficulty_id] = d.direction;
      }
      setDeltaOverrides(overrides);
      setDirections(dirs);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao analisar");
    } finally {
      setLoading(false);
    }
  }, [input, selectedMapId, token]);

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
        onApplied?.();
      } catch {
        setError("Falha ao aplicar");
      } finally {
        setApplying(null);
      }
    },
    [deltaOverrides, token, onApplied],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Análise manual de reweight</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Input de busca + colar ID */}
        <div ref={containerRef} className="relative w-full max-w-lg">
          <input
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setSelectedMapId(null);
              setData(null);
              setApplyResult(null);
            }}
            onKeyDown={(e) => e.key === "Enter" && runAnalyze()}
            placeholder="Buscar mapa rankeado ou colar BeatSaver ID/hash"
            className="w-full rounded-md border border-border-subtle bg-background px-3 py-1.5 pr-24 text-sm outline-none transition-colors focus:border-secondary"
          />
          <Button
            size="sm"
            onClick={runAnalyze}
            disabled={!token || loading || !input.trim()}
            className="absolute right-1.5 top-1/2 -translate-y-1/2"
          >
            {loading ? <Spinner size={12} /> : null}
            Analisar
          </Button>
          {searchOpen && searchResults.length > 0 ? (
            <ul className="absolute z-10 mt-1 w-full rounded-md border border-border-subtle bg-background shadow-lg">
              {searchResults.map((m) => (
                <li
                  key={m.id}
                  role="option"
                  className="cursor-pointer px-3 py-2 text-sm transition-colors hover:bg-surface-2"
                  onMouseDown={() => selectMap(m)}
                >
                  <span className="font-medium">{m.name}</span>
                  <span className="ml-2 text-xs text-muted">{m.mapper ?? "—"}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {selectedMapId ? (
            <p className="mt-1 text-xs text-muted">Mapa selecionado: #{selectedMapId}</p>
          ) : null}
        </div>

        {error ? <p className="text-sm text-danger">{error}</p> : null}

        {/* Resultado por dificuldade */}
        {data?.difficulties.map((d) => {
          const delta = deltaOverrides[d.difficulty_id] ?? 0;
          return (
            <div
              key={d.difficulty_id}
              className="rounded-lg border border-border-subtle bg-surface p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Badge>{d.name}</Badge>
                  {d.is_ranked ? null : <Badge variant="warning">não rankeada</Badge>}
                  <span className="text-xs text-muted">
                    atual: <span className="font-semibold tabular-nums">{d.current_stars ? formatNumber(d.current_stars) : "—"}★</span>
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {d.confidence !== "none" ? (
                    <>
                      <span className="text-xs text-muted">
                        amostra: {d.sample_size} · conf: {d.confidence}
                      </span>
                      <span className="text-xs text-muted">
                        acc {d.observed_acc != null ? formatNumber(d.observed_acc * 100) : "—"}%
                        {d.expected_acc != null
                          ? ` (esp. ${formatNumber(d.expected_acc * 100)}%)`
                          : ""}
                      </span>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-3">
                {/* Direção */}
                <div className="flex items-center gap-1 rounded-md border border-border-subtle bg-background px-1.5 py-0.5">
                  {["auto", "increase", "decrease"].map((dir) => {
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
                          if (dir === "increase" && d.current_stars) {
                            setDeltaOverrides((prev) => ({
                              ...prev,
                              [d.difficulty_id]: Math.max(0.05, prev[d.difficulty_id] ?? 0),
                            }));
                          } else if (dir === "decrease" && d.current_stars) {
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
                        className={`rounded px-2 py-0.5 text-xs font-semibold transition-colors ${
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

                {/* Delta stepper */}
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() =>
                      setDeltaOverrides((prev) => ({
                        ...prev,
                        [d.difficulty_id]: Math.round((prev[d.difficulty_id] - 0.1) * 100) / 100,
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
                    className="w-16 rounded border border-border-subtle bg-background px-1.5 py-0.5 text-center text-xs tabular-nums outline-none"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setDeltaOverrides((prev) => ({
                        ...prev,
                        [d.difficulty_id]: Math.round((prev[d.difficulty_id] + 0.1) * 100) / 100,
                      }))
                    }
                    className="flex h-6 w-6 items-center justify-center rounded border border-border-subtle text-xs hover:bg-surface-2"
                  >
                    +
                  </button>
                  <span className="text-xs text-muted">
                    → {d.current_stars != null ? formatNumber(d.current_stars + delta) : "—"}★
                  </span>
                </div>

                <Button
                  size="sm"
                  onClick={() => applyDelta(d.difficulty_id)}
                  disabled={applying === d.difficulty_id || !d.is_ranked}
                >
                  {applying === d.difficulty_id ? <Spinner size={12} /> : null}
                  Aplicar
                </Button>
              </div>
            </div>
          );
        })}

        {/* Resultado do apply */}
        {applyResult ? (
          <div className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm">
            {applyResult.old_stars}★ → {formatNumber(applyResult.new_stars)}★ ·
            {applyResult.scores_updated} scores recalculados ·
            {applyResult.players_affected} jogadores re-agregados
          </div>
        ) : null}
        {data && data.difficulties.length === 0 ? (
          <p className="text-sm text-muted">Nenhuma dificuldade disponível para análise.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}