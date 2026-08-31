"use client";

import { Fragment, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, getJson, postJson } from "@/lib/api";
import { AdminTabs, type AdminTab } from "./admin-tabs";
import { SuggestionsSection } from "./suggestions-section";
import type {
  AdminBatchItem,
  AdminBatchesResponse,
  AdminCandidate,
  AdminRankedMap,
  BatchStats,
  QualifyPreviewResponse,
  ReweightPreviewResponse,
  ReweightSuggestion,
  SuggestionsResponse,
} from "@/lib/types";
import { formatDateTime, formatInt, formatNumber } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

const TOKEN_KEY = "bsbr_admin_token";

const BATCH_LABELS: Record<string, string> = {
  sync_fetched: "Scores buscados",
  sync_inserted: "Scores inseridos",
  reweight_evaluated: "Dificuldades avaliadas",
  reweight_auto_applied: "Auto-aplicadas",
  reweight_pending: "Sugestões pendentes",
  players_updated: "Jogadores atualizados",
  snapshot_players: "Snapshots gravados",
  ratings_changed: "Mudanças de rating",
};

function pct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const scaled = value <= 1 ? value * 100 : value;
  return `${formatNumber(scaled)}%`;
}

function AdminDashboard() {
  const [tokenInput, setTokenInput] = useState("");
  const [token, setToken] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<ReweightSuggestion[] | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listInvalid, setListInvalid] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [actingId, setActingId] = useState<number | null>(null);

  const [collectLoading, setCollectLoading] = useState(false);
  const [collectError, setCollectError] = useState<string | null>(null);
  const [collectStats, setCollectStats] = useState<Record<string, number> | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<ReweightPreviewResponse | null>(null);

  const [batches, setBatches] = useState<AdminBatchItem[] | null>(null);
  const [batchesError, setBatchesError] = useState<string | null>(null);

  const [batchStats, setBatchStats] = useState<BatchStats | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [batchInvalid, setBatchInvalid] = useState(false);

  // Qualificação de mapas (nova batch)
  const [qualifySource, setQualifySource] = useState("");
  const [qualifyPreview, setQualifyPreview] = useState<QualifyPreviewResponse | null>(null);
  const [qualifyLoading, setQualifyLoading] = useState(false);
  const [qualifyError, setQualifyError] = useState<string | null>(null);
  const [qualifyInvalid, setQualifyInvalid] = useState(false);
  const [starsOverride, setStarsOverride] = useState<Record<string, string>>({});
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [queueSuccess, setQueueSuccess] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<AdminCandidate[] | null>(null);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [approveLoading, setApproveLoading] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [approveSuccess, setApproveSuccess] = useState<string | null>(null);
  const [qualifyExcluded, setQualifyExcluded] = useState<string[]>([]);
  const [excludedByMap, setExcludedByMap] = useState<Record<number, string[]>>({});
  const [rankToggling, setRankToggling] = useState<{ mapId: number; diffId: number } | null>(null);
  const [rankedMaps, setRankedMaps] = useState<AdminRankedMap[] | null>(null);
  const [rankedLoading, setRankedLoading] = useState(false);
  const [rankedError, setRankedError] = useState<string | null>(null);
  const [rankedQuery, setRankedQuery] = useState("");
  const [rankedTotal, setRankedTotal] = useState(0);
  const rankedDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [rejectLoading, setRejectLoading] = useState<number | null>(null);
  const [rejectError, setRejectError] = useState<string | null>(null);

  const tab = (useSearchParams().get("tab") ?? "qualification") as AdminTab;


  const loadSuggestions = useCallback(async (activeToken: string) => {
    setListLoading(true);
    setListInvalid(false);
    setListError(null);
    try {
      const data = await getJson<SuggestionsResponse>("/admin/reweight/suggestions", {
        headers: { "X-Admin-Token": activeToken },
      });
      setSuggestions(data.items);
    } catch (cause) {
      setSuggestions(null);
      if (cause instanceof ApiError && cause.status === 403) {
        setListInvalid(true);
      } else {
        setListError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao carregar sugestões.",
        );
      }
    } finally {
      setListLoading(false);
    }
  }, []);

  const runCollect = useCallback(async () => {
    if (!token) return;
    setCollectLoading(true);
    setCollectError(null);
    setCollectStats(null);
    try {
      const stats = await postJson<Record<string, number>>("/admin/reweight/collect", {
        auto_apply: false,
      }, { headers: { "X-Admin-Token": token } });
      setCollectStats(stats);
      await loadSuggestions(token);
    } catch (cause) {
      setCollectError(
        cause instanceof ApiError ? cause.message : "Falha ao coletar sugestões.",
      );
    } finally {
      setCollectLoading(false);
    }
  }, [token, loadSuggestions]);

  const runPreview = useCallback(async () => {
    if (!token) return;
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);
    try {
      const data = await postJson<ReweightPreviewResponse>("/admin/reweight/preview", {}, {
        headers: { "X-Admin-Token": token },
      });
      setPreviewData(data);
    } catch (cause) {
      setPreviewError(
        cause instanceof ApiError ? cause.message : "Falha ao simular o reweight.",
      );
    } finally {
      setPreviewLoading(false);
    }
  }, [token]);

  const loadBatches = useCallback(async (activeToken: string) => {
    setBatchesError(null);
    try {
      const data = await getJson<AdminBatchesResponse>("/admin/batches", {
        headers: { "X-Admin-Token": activeToken },
      });
      setBatches(data.items);
    } catch (cause) {
      setBatches(null);
      if (!(cause instanceof ApiError && cause.status === 403)) {
        setBatchesError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao carregar batches.",
        );
      }
    }
  }, []);

  const loadCandidates = useCallback(async (activeToken: string) => {
    setCandidatesError(null);
    try {
      const data = await getJson<{ items: AdminCandidate[] }>("/admin/maps/candidates", {
        headers: { "X-Admin-Token": activeToken },
      });
      setCandidates(data.items);
      setExcludedByMap((prev) => {
        const next: Record<number, string[]> = { ...prev };
        for (const item of data.items) {
          next[item.id] = item.difficulties.filter((d) => !d.is_ranked).map((d) => d.name);
        }
        return next;
      });
    } catch (cause) {
      if (!(cause instanceof ApiError && cause.status === 403)) {
        setCandidatesError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao carregar a fila.",
        );
      }
    }
  }, []);

  const loadRankedMaps = useCallback(
    async (
      activeToken: string,
      opts: { q?: string; offset?: number; append?: boolean } = {},
    ) => {
      setRankedLoading(true);
      setRankedError(null);
      try {
        const params = new URLSearchParams();
        const q = (opts.q ?? "").trim();
        if (q) params.set("q", q);
        params.set("limit", "50");
        params.set("offset", String(opts.offset ?? 0));
        const data = await getJson<{ items: AdminRankedMap[]; total: number }>(
          `/admin/maps/ranked?${params.toString()}`,
          { headers: { "X-Admin-Token": activeToken } },
        );
        setRankedMaps((prev) => (opts.append ? [...(prev ?? []), ...data.items] : data.items));
        setRankedTotal(data.total);
      } catch (cause) {
        if (!(cause instanceof ApiError && cause.status === 403)) {
          setRankedError(
            cause instanceof ApiError
              ? cause.message
              : "Falha de rede ao carregar mapas rankeados.",
          );
        }
      } finally {
        setRankedLoading(false);
      }
    },
    [],
  );

  const onRankedSearch = (value: string) => {
    setRankedQuery(value);
    if (rankedDebounceRef.current) clearTimeout(rankedDebounceRef.current);
    rankedDebounceRef.current = setTimeout(() => {
      void loadRankedMaps(token ?? "", { q: value });
    }, 300);
  };

  // Restaura token do sessionStorage e carrega a fila uma vez, fora do
  // caminho síncrono do efeito (react-hooks/set-state-in-effect).
  useEffect(() => {
    const id = setTimeout(() => {
      const stored = sessionStorage.getItem(TOKEN_KEY);
      if (!stored) return;
      setTokenInput(stored);
      setToken(stored);
      void loadSuggestions(stored);
      void loadBatches(stored);
      void loadCandidates(stored);
      void loadRankedMaps(stored);
    }, 0);
    return () => clearTimeout(id);
  }, [loadSuggestions, loadBatches, loadCandidates]);

  function saveToken(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = tokenInput.trim();
    if (!trimmed) return;
    sessionStorage.setItem(TOKEN_KEY, trimmed);
    setSuggestions(null);
    setBatches(null);
    setBatchStats(null);
    setBatchError(null);
    setBatchInvalid(false);
    setToken(trimmed);
    void loadSuggestions(trimmed);
    void loadBatches(trimmed);
    void loadCandidates(trimmed);
    void loadRankedMaps(trimmed);
  }

  async function act(suggestion: ReweightSuggestion, action: "apply" | "reject") {
    if (!token) return;
    setActingId(suggestion.id);
    try {
      await postJson(`/admin/reweight/${suggestion.id}/${action}`, {}, {
        headers: { "X-Admin-Token": token },
      });
      await loadSuggestions(token);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) {
        setListInvalid(true);
      } else {
        setListError(
          cause instanceof ApiError
            ? `Falha ao ${action === "apply" ? "aplicar" : "rejeitar"}: ${cause.message}`
            : "Falha de rede na ação.",
        );
      }
    } finally {
      setActingId(null);
    }
  }

  async function runBatch() {
    if (!token) return;
    setBatchLoading(true);
    setBatchError(null);
    setBatchInvalid(false);
    try {
      const stats = await postJson<BatchStats>("/admin/batch/run", {}, {
        headers: { "X-Admin-Token": token },
        timeoutMs: 90_000, // batch roda sync completo inline; > 10s default
      });
      setBatchStats(stats);
      if (token) void loadBatches(token);
    } catch (cause) {
      setBatchStats(null);
      if (cause instanceof ApiError && cause.status === 403) {
        setBatchInvalid(true);
      } else {
        setBatchError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao rodar o batch.",
        );
      }
    } finally {
      setBatchLoading(false);
    }
  }

  async function runQualifyWith(source: string) {
    if (!token || !source.trim()) return;
    setQualifyLoading(true);
    setQualifyError(null);
    setQualifyInvalid(false);
    setQualifyPreview(null);
    setStarsOverride({});
    setQueueError(null);
    setQueueSuccess(null);
    try {
      const preview = await postJson<QualifyPreviewResponse>(
        "/admin/maps/qualify",
        { source: source.trim() },
        { headers: { "X-Admin-Token": token } },
      );
      setQualifyPreview(preview);
      setQualifyExcluded(
        preview.difficulties.filter((d) => !d.is_ranked).map((d) => d.name),
      );
      setStarsOverride(
        Object.fromEntries(
          preview.difficulties.map((d) => [
            d.name,
            d.total_stars != null ? String(d.total_stars) : "",
          ]),
        ),
      );
    } catch (cause) {
      setQualifyPreview(null);
      if (cause instanceof ApiError && cause.status === 403) {
        setQualifyInvalid(true);
      } else {
        setQualifyError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao analisar o mapa.",
        );
      }
    } finally {
      setQualifyLoading(false);
    }
  }

  async function runQualify() {
    await runQualifyWith(qualifySource);
  }

  /** Candidato vindo de sugestão aprovada (sem difficulties): roda o ML nele. */
  async function runQualifyForCandidate(hash: string) {
    setQualifySource(hash);
    await runQualifyWith(hash);
    document
      .getElementById("qualify-entry")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function runQueueFor(mapId: number) {
    if (!token) return;
    setQueueLoading(true);
    setQueueError(null);
    setQueueSuccess(null);
    try {
      const result = await postJson<{ id: number; status: string }>(
        `/admin/maps/${mapId}/qualify`,
        {},
        { headers: { "X-Admin-Token": token } },
      );
      setQueueSuccess(`Mapa #${result.id} colocado na fila de qualificação (status ${result.status}).`);
      void loadCandidates(token);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) {
        setQueueError("Token inválido (403).");
      } else {
        setQueueError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao colocar na fila.",
        );
      }
    } finally {
      setQueueLoading(false);
    }
  }

  async function runQueue() {
    if (!token || !qualifyPreview) return;
    setQueueLoading(true);
    setQueueError(null);
    setQueueSuccess(null);
    try {
      // Aplica o ajuste manual de estrelas antes de colocar na fila
      const overrides: Record<string, number> = {};
      for (const [name, value] of Object.entries(starsOverride)) {
        const parsed = Number.parseFloat(value);
        if (Number.isFinite(parsed) && parsed > 0) overrides[name] = parsed;
      }
      const result = await postJson<{ id: number; status: string }>(
        `/admin/maps/${qualifyPreview.map.id}/qualify`,
        { stars_override: overrides, excluded_difficulties: qualifyExcluded },
        { headers: { "X-Admin-Token": token } },
      );
      setQueueSuccess(
        `Mapa #${result.id} colocado na fila de qualificação (status ${result.status}).`,
      );
      void loadCandidates(token);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) {
        setQueueError("Token inválido (403).");
      } else {
        setQueueError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao colocar na fila.",
        );
      }
    } finally {
      setQueueLoading(false);
    }
  }

  async function runReject(mapId: number) {
    if (!token) return;
    setRejectLoading(mapId);
    setRejectError(null);
    setApproveError(null);
    try {
      const result = await postJson<{ id: number; status: string }>(
        `/admin/maps/${mapId}/reject`,
        {},
        { headers: { "X-Admin-Token": token } },
      );
      setApproveSuccess(
        `Mapa #${result.id} recusado (status ${result.status}).`,
      );
      void loadCandidates(token);
    } catch (cause) {
      setApproveSuccess(null);
      if (cause instanceof ApiError && cause.status === 403) {
        setRejectError("Token inválido (403).");
      } else {
        setRejectError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao recusar o mapa.",
        );
      }
    } finally {
      setRejectLoading(null);
    }
  }

  async function runApprove(mapId: number) {
    if (!token) return;
    setApproveLoading(true);
    setApproveError(null);
    setApproveSuccess(null);
    try {
      const result = await postJson<{ id: number; status: string }>(
        `/admin/maps/${mapId}/approve`,
        {
          ss_leaderboard_ids: {},
          reviewer: "staff",
          excluded_difficulties: excludedByMap[mapId] ?? [],
        },
        { headers: { "X-Admin-Token": token } },
      );
      setApproveSuccess(
        `Mapa #${result.id} aprovado (status ${result.status}). Lembre de rodar o batch para sincronizar scores.`,
      );
      void loadCandidates(token);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) {
        setApproveError("Token inválido (403).");
      } else {
        setApproveError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao aprovar o mapa.",
        );
      }
    } finally {
      setApproveLoading(false);
    }
  }

  function setCandExcluded(mapId: number, name: string, excluded: boolean) {
    setExcludedByMap((prev) => {
      const current = new Set(prev[mapId] ?? []);
      if (excluded) current.add(name);
      else current.delete(name);
      return { ...prev, [mapId]: [...current] };
    });
  }

  async function toggleDifficultyRank(
    mapId: number,
    diff: { id: number; name: string; total_stars: number | null; is_ranked: boolean },
    ranked: boolean,
  ) {
    if (!token) return;
    setRankToggling({ mapId, diffId: diff.id });
    setApproveError(null);
    try {
      await postJson(
        `/admin/maps/${mapId}/difficulties/${diff.id}/rank`,
        { ranked },
        { headers: { "X-Admin-Token": token } },
      );
      await loadCandidates(token);
      await loadRankedMaps(token, { q: rankedQuery });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) {
        setApproveError("Token inválido (403).");
      } else {
        setApproveError(
          cause instanceof ApiError
            ? cause.message
            : "Falha de rede ao alterar a dificuldade.",
        );
      }
    } finally {
      setRankToggling(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-black tracking-tight">Administração</h1>
        <p className="mt-1 text-sm text-muted">
          Qualificação, sugestões da comunidade, reweight e batch semanal.
        </p>
      </div>

      <AdminTabs active={tab} />

      {/* Token */}
      <Card>
        <CardHeader>
          <CardTitle>X-Admin-Token</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={saveToken} className="flex items-end gap-2">
            <label className="flex flex-1 flex-col gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
              Token salvo neste navegador (sessionStorage)
              <input
                type="password"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                placeholder="cole o token aqui"
                autoComplete="off"
                className="h-9 w-full rounded-md border border-border-subtle bg-background px-3 font-mono text-sm text-foreground placeholder:text-muted/60 focus:border-secondary focus:outline-none"
              />
            </label>
            <Button type="submit" disabled={!tokenInput.trim()}>
              Salvar
            </Button>
            {token ? (
              <Badge variant="success">token ativo</Badge>
            ) : (
              <Badge variant="warning">sem token</Badge>
            )}
          </form>
        </CardContent>
      </Card>

      <div hidden={tab !== "reweight"} className="flex flex-col gap-6">
      {/* Fila de reweight */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Sugestões de reweight (pendentes)</CardTitle>
          {token ? (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={runPreview} disabled={previewLoading}>
                {previewLoading ? <Spinner size={14} /> : null}
                Prévia (simular)
              </Button>
              <Button variant="ghost" size="sm" onClick={runCollect} disabled={collectLoading}>
                {collectLoading ? <Spinner size={14} /> : null}
                Coletar sugestões
              </Button>
              <Button variant="ghost" size="sm" onClick={() => loadSuggestions(token)}>
                Recarregar
              </Button>
            </div>
          ) : null}
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {collectError ? (
            <p role="alert" className="text-sm font-medium text-danger">{collectError}</p>
          ) : null}
          {collectStats ? (
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge variant="secondary">{collectStats.evaluated ?? 0} avaliadas</Badge>
              <Badge variant="warning">{collectStats.pending ?? 0} pendentes</Badge>
              <Badge variant="success">{collectStats.auto_applied ?? 0} auto-aplicadas</Badge>
            </div>
          ) : null}
          {!token ? (
            <p className="py-4 text-sm text-muted">
              Informe o X-Admin-Token acima para ver a fila.
            </p>
          ) : listLoading ? (
            <div className="flex items-center justify-center gap-3 py-8 text-muted">
              <Spinner size={20} />
              <span className="text-sm">Carregando sugestões…</span>
            </div>
          ) : listInvalid ? (
            <p role="alert" className="py-4 text-sm font-medium text-danger">
              Token inválido (403). Confira o valor salvo e tente novamente.
            </p>
          ) : listError ? (
            <p role="alert" className="py-4 text-sm text-danger">
              {listError}
            </p>
          ) : suggestions && suggestions.length > 0 ? (
            <ul className="flex flex-col divide-y divide-border-subtle/60">
              {suggestions.map((suggestion) => {
                const delta =
                  suggestion.suggested_stars !== null && suggestion.current_stars !== null
                    ? suggestion.suggested_stars - suggestion.current_stars
                    : null;
                return (
                  <li
                    key={suggestion.id}
                    className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold">{suggestion.map_name ?? `Diff #${suggestion.difficulty_id}`}</span>
                        <Badge>{suggestion.difficulty}</Badge>
                        <span className="text-sm tabular-nums">
                          <span className="text-muted">{formatNumber(suggestion.current_stars)}</span>
                          {" → "}
                          <span className={delta !== null && delta > 0 ? "font-bold text-success" : delta !== null && delta < 0 ? "font-bold text-danger" : ""}>
                            {formatNumber(suggestion.suggested_stars)}
                          </span>
                          {delta !== null && delta !== 0 ? (
                            <span className={delta > 0 ? "ml-1 text-xs text-success" : "ml-1 text-xs text-danger"}>
                              ({delta > 0 ? "+" : ""}
                              {formatNumber(delta)})
                            </span>
                          ) : null}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted" title={suggestion.reason}>
                        {suggestion.reason}
                      </p>
                      <p className="mt-0.5 text-[11px] text-muted/70 tabular-nums">
                        amostra {formatInt(suggestion.sample_size)} · confiança {pct(suggestion.confidence)} · acc observada {pct(suggestion.observed_acc)} vs esperada {pct(suggestion.expected_acc)}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        onClick={() => act(suggestion, "apply")}
                        disabled={actingId !== null}
                      >
                        {actingId === suggestion.id ? <Spinner size={12} /> : null}
                        Aplicar
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => act(suggestion, "reject")}
                        disabled={actingId !== null}
                      >
                        Rejeitar
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="py-4 text-sm text-muted">
              Nenhuma sugestão pendente. A fila é populada pelo batch semanal.
            </p>
          )}

          {previewError ? (
            <p role="alert" className="border-t border-border-subtle pt-3 text-sm font-medium text-danger">
              {previewError}
            </p>
          ) : null}

          {previewData ? (
            <div className="flex flex-col gap-4 border-t border-border-subtle pt-4">
              <div>
                <h3 className="mb-2 text-sm font-bold uppercase tracking-wider text-muted">
                  Impacto por dificuldade ({formatInt(previewData.difficulties.length)})
                </h3>
                {previewData.difficulties.length === 0 ? (
                  <p className="text-sm text-muted">Nenhuma dificuldade com amostra suficiente para sugestão.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[680px] text-sm">
                      <thead>
                        <tr className="border-b border-border-subtle text-left text-[11px] uppercase tracking-wider text-muted">
                          <th className="py-2 pr-3 font-bold">Mapa</th>
                          <th className="py-2 pr-3 font-bold">Diff</th>
                          <th className="py-2 pr-3 text-right font-bold">Stars</th>
                          <th className="py-2 pr-3 text-right font-bold">Sugerido</th>
                          <th className="py-2 pr-3 text-right font-bold">Δ</th>
                          <th className="py-2 pr-3 text-center font-bold">Conf</th>
                          <th className="py-2 pr-3 text-center font-bold">Auto</th>
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.difficulties.map((d) => (
                          <tr key={d.difficulty_id} className="border-b border-border-subtle/50 last:border-b-0">
                            <td className="py-2 pr-3 font-medium">{d.map_name}</td>
                            <td className="py-2 pr-3 text-muted">{d.difficulty}</td>
                            <td className="py-2 pr-3 text-right tabular-nums">{formatNumber(d.current_stars)}</td>
                            <td className="py-2 pr-3 text-right font-bold tabular-nums">
                              {formatNumber(d.suggested_stars)}
                            </td>
                            <td className={`py-2 pr-3 text-right font-bold tabular-nums ${d.delta_stars > 0 ? "text-success" : d.delta_stars < 0 ? "text-danger" : ""}`}>
                              {d.delta_stars > 0 ? "+" : ""}{formatNumber(d.delta_stars)}
                            </td>
                            <td className="py-2 pr-3 text-center text-xs">{d.confidence}</td>
                            <td className="py-2 pr-3 text-center">
                              {d.auto_appliable ? <Badge variant="success">sim</Badge> : <span className="text-muted/40">—</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div>
                <h3 className="mb-2 text-sm font-bold uppercase tracking-wider text-muted">
                  Ranking simulado (top {formatInt(previewData.ranking.length)})
                </h3>
                {previewData.ranking.length === 0 ? (
                  <p className="text-sm text-muted">Nenhuma mudança de posição/PP no topo do ranking.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[560px] text-sm">
                      <thead>
                        <tr className="border-b border-border-subtle text-left text-[11px] uppercase tracking-wider text-muted">
                          <th className="py-2 pr-3 font-bold">Jogador</th>
                          <th className="py-2 pr-3 text-center font-bold">Rank</th>
                          <th className="py-2 pr-3 text-right font-bold">PP</th>
                          <th className="py-2 pr-3 text-right font-bold">Δ</th>
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.ranking.map((row) => (
                          <tr key={row.name} className="border-b border-border-subtle/50 last:border-b-0">
                            <td className="py-2 pr-3 font-medium">{row.name}</td>
                            <td className="py-2 pr-3 text-center tabular-nums">
                              {row.rank_before !== row.rank_after ? (
                                <span>
                                  <span className="text-muted">#{row.rank_before}</span>
                                  {" → "}
                                  <span className={`font-bold ${row.rank_after! < row.rank_before! ? "text-success" : "text-danger"}`}>
                                    #{row.rank_after}
                                  </span>
                                </span>
                              ) : (
                                <span className="text-muted">#{row.rank_after}</span>
                              )}
                            </td>
                            <td className="py-2 pr-3 text-right tabular-nums">
                              {formatNumber(row.pp_before)} → {formatNumber(row.pp_after)}
                            </td>
                            <td className={`py-2 pr-3 text-right font-bold tabular-nums ${row.delta_pp > 0 ? "text-success" : row.delta_pp < 0 ? "text-danger" : "text-muted"}`}>
                              {row.delta_pp > 0 ? "+" : ""}{formatNumber(row.delta_pp)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
      </div>

      <div hidden={tab !== "qualification"} className="flex flex-col gap-6">
      {/* Qualificação de mapas (nova batch) */}
      <Card id="qualify-entry">
        <CardHeader>
          <CardTitle>Entrada de mapas (qualificação)</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <input
              value={qualifySource}
              onChange={(e) => setQualifySource(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runQualify()}
              placeholder="ID do BeatSaver ou hash (40 hex)"
              disabled={!token || qualifyLoading}
              className="w-full max-w-sm rounded-md border border-border-subtle bg-background px-3 py-1.5 text-sm outline-none transition-colors focus:border-secondary sm:w-72"
            />
            <Button onClick={runQualify} disabled={!token || qualifyLoading || !qualifySource.trim()}>
              {qualifyLoading ? <Spinner size={14} /> : null}
              Analisar com o ML
            </Button>
            {!token ? (
              <span className="text-sm text-muted">requer token</span>
            ) : null}
            {qualifyInvalid ? (
              <span role="alert" className="text-sm font-medium text-danger">
                Token inválido (403).
              </span>
            ) : null}
            {qualifyError ? (
              <span role="alert" className="text-sm text-danger">{qualifyError}</span>
            ) : null}
          </div>

          {qualifyPreview ? (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <span className="font-bold">{qualifyPreview.map.name}</span>
                {qualifyPreview.map.mapper ? (
                  <span className="text-muted">mapper: {qualifyPreview.map.mapper}</span>
                ) : null}
                {qualifyPreview.map.bpm ? (
                  <span className="text-muted">{Math.round(qualifyPreview.map.bpm)} BPM</span>
                ) : null}
                <Badge variant={qualifyPreview.map.status === "ranked" ? "success" : "warning"}>
                  {qualifyPreview.map.status}
                </Badge>
                {qualifyPreview.created ? (
                  <span className="text-xs text-muted">novo candidato (preview das predições do ML)</span>
                ) : null}
              </div>

              <div className="overflow-x-auto rounded-lg border border-border-subtle">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border-subtle bg-surface text-left text-xs uppercase tracking-wider text-muted">
                      <th scope="col" className="px-4 py-2 font-semibold">Rankear</th>
                      <th scope="col" className="px-4 py-2 font-semibold">Dificuldade</th>
                      <th scope="col" className="px-4 py-2 text-right font-semibold">Stars (ML)</th>
                      <th scope="col" className="hidden px-4 py-2 text-right font-semibold sm:table-cell">Acc</th>
                      <th scope="col" className="hidden px-4 py-2 text-right font-semibold sm:table-cell">Tech</th>
                      <th scope="col" className="hidden px-4 py-2 text-right font-semibold sm:table-cell">Speed</th>
                      <th scope="col" className="hidden px-4 py-2 font-semibold lg:table-cell">Estilo</th>
                      <th scope="col" className="hidden px-4 py-2 text-right font-semibold md:table-cell">NPS</th>
                      <th scope="col" className="px-4 py-2 font-semibold">Leaderboard ScoreSaber</th>
                    </tr>
                  </thead>
                  <tbody>
                    {qualifyPreview.difficulties.map((d) => {
                      const excluded = qualifyExcluded.includes(d.name);
                      return (
                      <tr
                        key={d.id}
                        className={`border-b border-border-subtle/60 last:border-b-0 ${excluded ? "opacity-60" : ""}`}
                      >
                        <td className="px-4 py-2">
                          <input
                            type="checkbox"
                            checked={!excluded}
                            onChange={(e) =>
                              setQualifyExcluded((prev) =>
                                e.target.checked
                                  ? prev.filter((n) => n !== d.name)
                                  : [...prev, d.name],
                              )
                            }
                            aria-label={`Rankear dificuldade ${d.name}`}
                            className="h-4 w-4 cursor-pointer accent-[var(--secondary)]"
                          />
                        </td>
                        <td className="px-4 py-2 font-medium">
                          {d.name}
                          {excluded ? (
                            <span className="ml-2 text-xs font-semibold text-danger">fora do ranking</span>
                          ) : null}
                        </td>
                        <td className="px-4 py-2 text-right">
                          <input
                            value={starsOverride[d.name] ?? ""}
                            onChange={(e) =>
                              setStarsOverride((prev) => ({ ...prev, [d.name]: e.target.value }))
                            }
                            inputMode="decimal"
                            title="Ajuste manual das estrelas (pedir ao ML subir/descer)"
                            className="w-20 rounded-md border border-border-subtle bg-background px-2 py-1 text-right text-sm font-bold tabular-nums outline-none transition-colors focus:border-secondary"
                          />
                        </td>
                        <td className="hidden px-4 py-2 text-right text-xs tabular-nums text-muted sm:table-cell">
                          {d.acc_stars != null ? d.acc_stars.toFixed(1) : "—"}
                        </td>
                        <td className="hidden px-4 py-2 text-right text-xs tabular-nums text-muted sm:table-cell">
                          {d.tech_stars != null ? d.tech_stars.toFixed(1) : "—"}
                        </td>
                        <td className="hidden px-4 py-2 text-right text-xs tabular-nums text-muted sm:table-cell">
                          {d.speed_stars != null ? d.speed_stars.toFixed(1) : "—"}
                        </td>
                        <td className="hidden px-4 py-2 text-xs text-muted lg:table-cell">
                          {(d.style_tags ?? []).join(", ") || "—"}
                        </td>
                        <td className="hidden px-4 py-2 text-right tabular-nums text-muted md:table-cell">
                          {d.nps != null ? d.nps.toFixed(1) : "—"}
                        </td>
                        <td className="px-4 py-2 font-mono text-xs text-muted">
                          {d.ss_leaderboard_id ?? (
                            <span className="text-warning">não encontrado no ScoreSaber</span>
                          )}
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  onClick={runQueue}
                  disabled={!token || queueLoading}
                  variant="secondary"
                >
                  {queueLoading ? <Spinner size={14} /> : null}
                  Colocar na fila de qualify
                </Button>
                <span className="text-xs text-muted">
                  Desmarque dificuldades inviáveis (Lightshow, dificuldades sem
                  leaderboard). Edite o campo Stars para pedir ao ML um ajuste.
                </span>
                {queueError ? (
                  <span role="alert" className="text-sm text-danger">{queueError}</span>
                ) : null}
                {queueSuccess ? (
                  <span role="status" className="text-sm text-emerald-600">{queueSuccess}</span>
                ) : null}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Fila de qualificação */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Fila de qualificação</CardTitle>
          {token ? (
            <Button variant="ghost" size="sm" onClick={() => loadCandidates(token)}>
              Recarregar
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {!token ? (
            <p className="py-4 text-sm text-muted">
              Informe o X-Admin-Token acima para ver a fila.
            </p>
          ) : candidatesError ? (
            <p role="alert" className="py-4 text-sm text-danger">{candidatesError}</p>
          ) : candidates === null ? (
            <p className="py-4 text-sm text-muted">Carregando…</p>
          ) : candidates.length === 0 ? (
            <p className="py-4 text-sm text-muted">
              Nenhum candidato na fila. Analise um mapa acima para começar.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border-subtle">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle bg-surface text-left text-xs uppercase tracking-wider text-muted">
                    <th scope="col" className="px-4 py-2.5 font-semibold">Mapa</th>
                    <th scope="col" className="hidden px-4 py-2.5 font-semibold sm:table-cell">Mapper</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Status</th>
                    <th scope="col" className="hidden px-4 py-2.5 font-semibold md:table-cell">BPM</th>
                    <th scope="col" className="hidden px-4 py-2.5 font-semibold md:table-cell">Enviado por</th>
                    <th scope="col" className="px-4 py-2.5 text-right font-semibold">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((cand) => {
                    const isRankedMap = cand.status === "ranked";
                    const candExcluded = excludedByMap[cand.id] ?? [];
                    return (
                      <Fragment key={cand.id}>
                      <tr className="border-b border-border-subtle/60">
                        <td className="px-4 py-2.5 font-medium">
                          <span className="block max-w-56 truncate">{cand.name}</span>
                        </td>
                        <td className="hidden px-4 py-2.5 text-muted sm:table-cell">
                          {cand.mapper ?? "—"}
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge variant={cand.status === "ranked" ? "success" : cand.status === "qualified" ? "secondary" : "warning"}>
                            {cand.status === "ranked" ? "rankeado" : cand.status === "qualified" ? "na fila" : "candidato"}
                          </Badge>
                        </td>
                        <td className="hidden px-4 py-2.5 tabular-nums text-muted md:table-cell">
                          {cand.bpm ? Math.round(cand.bpm) : "—"}
                        </td>
                        <td className="hidden px-4 py-2.5 text-muted md:table-cell">
                          {cand.submitted_by ?? "—"}
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center justify-end gap-2">
                            {cand.status === "qualified" ? (
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => runApprove(cand.id)}
                                disabled={!token || approveLoading}
                              >
                                {approveLoading ? <Spinner size={12} /> : null}
                                Aprovar
                              </Button>
                            ) : cand.status === "candidate" ? (
                              <>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => runQualifyForCandidate(cand.hash)}
                                  disabled={!token || qualifyLoading}
                                >
                                  {qualifyLoading ? <Spinner size={12} /> : null}
                                  Analisar com o ML
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={() => runQueueFor(cand.id)}
                                  disabled={!token || queueLoading}
                                >
                                  {queueLoading ? <Spinner size={12} /> : null}
                                  Colocar na fila
                                </Button>
                              </>
                            ) : null}
                            {!isRankedMap ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => runReject(cand.id)}
                                disabled={!token || rejectLoading === cand.id}
                                className="text-danger hover:text-danger"
                              >
                                {rejectLoading === cand.id ? <Spinner size={12} /> : null}
                                Recusar
                              </Button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                      <tr className="border-b border-border-subtle/30 last:border-b-0">
                        <td colSpan={6} className="bg-background/40 px-4 py-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
                              Dificuldades
                            </span>
                            {cand.difficulties.length === 0 ? (
                              <span className="text-xs text-warning">
                                sem análise — clique em "Analisar com o ML"
                              </span>
                            ) : (
                              cand.difficulties.map((d) => {
                                const excluded = candExcluded.includes(d.name);
                                const toggling = rankToggling?.diffId === d.id;
                                return (
                                  <label
                                    key={d.id}
                                    className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors ${
                                      excluded
                                        ? "border-border-subtle bg-background/60 text-muted line-through"
                                        : "border-border-subtle bg-surface text-foreground"
                                    }`}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={!excluded}
                                      onChange={(e) =>
                                        setCandExcluded(cand.id, d.name, !e.target.checked)
                                      }
                                      aria-label={`Rankear ${d.name} de ${cand.name}`}
                                      className="h-3.5 w-3.5 cursor-pointer accent-[var(--secondary)]"
                                    />
                                    <span className="font-semibold">{d.name}</span>
                                    <span className="tabular-nums text-muted">
                                      {d.total_stars != null ? formatNumber(d.total_stars) : "—"}★
                                    </span>
                                    {excluded ? (
                                      <span className="font-semibold text-danger">fora</span>
                                    ) : null}
                                    {toggling ? <Spinner size={10} /> : null}
                                  </label>
                                );
                              })
                            )}
                          </div>
                        </td>
                      </tr>
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {rejectError ? (
            <p role="alert" className="mt-3 text-sm text-danger">{rejectError}</p>
          ) : null}
          {approveError ? (
            <p role="alert" className="mt-3 text-sm text-danger">{approveError}</p>
          ) : null}
          {approveSuccess ? (
            <p role="status" className="mt-3 text-sm text-emerald-600">{approveSuccess}</p>
          ) : null}
        </CardContent>
      </Card>

      {/* Mapas rankeados — remover dificuldades inviáveis */}
      <Card>
        <CardHeader>
          <CardTitle>Mapas rankeados — dificuldades</CardTitle>
          <p className="text-sm text-muted">
            Desative dificuldades inviáveis (is_ranked=false): elas somem do ranking,
            reweight, playlists e leaderboards, sem recusar o mapa.
          </p>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {!token ? (
            <p className="text-sm text-muted">Informe o X-Admin-Token acima para gerenciar.</p>
          ) : (
            <>
              <div className="relative flex max-w-sm items-center">
                <svg
                  aria-hidden="true"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="pointer-events-none absolute left-3 h-4 w-4 text-muted"
                >
                  <path
                    fillRule="evenodd"
                    d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"
                    clipRule="evenodd"
                  />
                </svg>
                <input
                  type="search"
                  value={rankedQuery}
                  onChange={(e) => onRankedSearch(e.target.value)}
                  placeholder="Buscar mapa rankeado…"
                  aria-label="Buscar mapa rankeado"
                  className="h-9 w-full rounded-md border border-border-subtle bg-surface pl-9 pr-3 text-sm text-foreground placeholder:text-muted focus:border-secondary focus:outline-none"
                />
              </div>
              {rankedMaps && rankedMaps.length > 0 ? (
                <p className="text-xs text-muted">
                  Exibindo {rankedMaps.length} de {rankedTotal} mapas rankeados
                  {rankedQuery.trim() ? ` (buscando “${rankedQuery.trim()}”)` : ""}.
                </p>
              ) : null}
            </>
          )}
          {rankedLoading && !rankedMaps ? (
            <p className="flex items-center gap-2 text-sm text-muted">
              <Spinner size={14} /> carregando mapas rankeados…
            </p>
          ) : rankedError ? (
            <p role="alert" className="text-sm text-danger">{rankedError}</p>
          ) : !rankedMaps || rankedMaps.length === 0 ? (
            <p className="text-sm text-muted">
              {rankedQuery.trim() ? "Nenhum mapa rankeado com essa busca." : "Nenhum mapa rankeado."}
            </p>
          ) : (
            <>
            <div className="flex flex-col gap-2">
              {rankedMaps.map((m) => (
                <div
                  key={m.id}
                  className="flex flex-col gap-1.5 rounded-lg border border-border-subtle bg-background/40 px-3 py-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-semibold">{m.name}</span>
                    {m.mapper ? <span className="text-xs text-muted">{m.mapper}</span> : null}
                    <span className="text-xs tabular-nums text-muted">
                      {m.difficulties.filter((d) => d.is_ranked).length}/{m.difficulties.length} rankeadas
                    </span>
                  </div>
                  {m.difficulties.length === 0 ? (
                    <span className="text-xs text-muted">sem dificuldades Standard</span>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {m.difficulties.map((d) => {
                        const toggling = rankToggling?.mapId === m.id && rankToggling?.diffId === d.id;
                        return (
                          <label
                            key={d.id}
                            className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors ${
                              d.is_ranked
                                ? "border-border-subtle bg-surface text-foreground"
                                : "border-border-subtle bg-background/60 text-muted line-through"
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={d.is_ranked}
                              disabled={toggling}
                              onChange={(e) => void toggleDifficultyRank(m.id, d, e.target.checked)}
                              aria-label={`Rankear ${d.name} de ${m.name}`}
                              className="h-3.5 w-3.5 cursor-pointer accent-[var(--secondary)]"
                            />
                            <span className="font-semibold">{d.name}</span>
                            <span className="tabular-nums text-muted">
                              {d.total_stars != null ? formatNumber(d.total_stars) : "—"}★
                            </span>
                            {!d.is_ranked ? (
                              <span className="font-semibold text-danger">fora</span>
                            ) : null}
                            {toggling ? <Spinner size={10} /> : null}
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {rankedMaps && rankedMaps.length < rankedTotal ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() =>
                  void loadRankedMaps(token ?? "", {
                    q: rankedQuery,
                    offset: rankedMaps.length,
                    append: true,
                  })
                }
                disabled={rankedLoading}
              >
                {rankedLoading ? <Spinner size={12} /> : null}
                Carregar mais ({rankedTotal - rankedMaps.length} restantes)
              </Button>
            ) : null}
            </>
          )}
        </CardContent>
      </Card>
      </div>

      <div hidden={tab !== "batch"} className="flex flex-col gap-6">
      {/* Batch */}
      <Card>
        <CardHeader>
          <CardTitle>Batch semanal</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={runBatch} disabled={!token || batchLoading}>
              {batchLoading ? <Spinner size={14} /> : null}
              Rodar batch agora
            </Button>
            {!token ? (
              <span className="text-sm text-muted">requer token</span>
            ) : batchLoading ? (
              <span className="text-sm text-muted">
                Executando pipeline completa (sync → reweight → ranking → snapshot)…
              </span>
            ) : null}
            {batchInvalid ? (
              <span role="alert" className="text-sm font-medium text-danger">
                Token inválido (403).
              </span>
            ) : null}
            {batchError ? (
              <span role="alert" className="text-sm text-danger">
                {batchError}
              </span>
            ) : null}
          </div>

          {batchStats ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(batchStats).map(([key, value]) => (
                <div key={key} className="rounded-md bg-background px-3 py-2">
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-muted">
                    {BATCH_LABELS[key] ?? key}
                  </span>
                  <span className="text-lg font-bold tabular-nums">{formatInt(value)}</span>
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Histórico de batches */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Histórico de batches</CardTitle>
          {token ? (
            <Button variant="ghost" size="sm" onClick={() => loadBatches(token)}>
              Recarregar
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {!token ? (
            <p className="py-4 text-sm text-muted">
              Informe o X-Admin-Token acima para ver o histórico.
            </p>
          ) : batchesError ? (
            <p role="alert" className="py-4 text-sm text-danger">{batchesError}</p>
          ) : batches === null ? (
            <p className="py-4 text-sm text-muted">Carregando…</p>
          ) : batches.length === 0 ? (
            <p className="py-4 text-sm text-muted">Nenhum batch executado ainda.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border-subtle">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle bg-surface text-left text-xs uppercase tracking-wider text-muted">
                    <th scope="col" className="px-4 py-2.5 font-semibold">#</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Tipo</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Início</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Fim</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Status</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  {batches.map((batch) => (
                    <tr
                      key={batch.id}
                      className="border-b border-border-subtle/60 last:border-b-0"
                    >
                      <td className="px-4 py-2.5 tabular-nums text-muted">{batch.id}</td>
                      <td className="px-4 py-2.5 capitalize">{batch.kind}</td>
                      <td className="px-4 py-2.5 tabular-nums text-muted">
                        {formatDateTime(batch.started_at)}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-muted">
                        {batch.running ? "—" : formatDateTime(batch.finished_at)}
                      </td>
                      <td className="px-4 py-2.5">
                        {batch.running ? (
                          <Badge variant="warning">em execução</Badge>
                        ) : (
                          <Badge variant="success">concluído</Badge>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted">
                        {batch.stats
                          ? [
                              ["sync_inserted", "scores"],
                              ["reweight_pending", "sugestões"],
                              ["snapshot_players", "snapshots"],
                              ["ratings_changed", "ratings"],
                            ]
                              .map(([key, label]) => {
                                const value = batch.stats?.[key];
                                return value ? `${formatInt(value)} ${label}` : null;
                              })
                              .filter(Boolean)
                              .join(" · ")
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      </div>

      {tab === "suggestions" ? <SuggestionsSection token={token} /> : null}
    </div>
  );
}

function AdminPage() {
  return (
    <Suspense
      fallback={
        <div className="p-8 text-center text-sm text-muted">Carregando admin…</div>
      }
    >
      <AdminDashboard />
    </Suspense>
  );
}

export default AdminPage;
