"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getJson, postJson } from "@/lib/api";
import type {
  AdminBatchItem,
  AdminBatchesResponse,
  AdminCandidate,
  BatchStats,
  QualifyPreviewResponse,
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

export default function AdminPage() {
  const [tokenInput, setTokenInput] = useState("");
  const [token, setToken] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<ReweightSuggestion[] | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listInvalid, setListInvalid] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [actingId, setActingId] = useState<number | null>(null);

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
  const [rejectLoading, setRejectLoading] = useState<number | null>(null);
  const [rejectError, setRejectError] = useState<string | null>(null);


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
    } catch (cause) {
      if (!(cause instanceof ApiError && cause.status === 403)) {
        setCandidatesError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao carregar a fila.",
        );
      }
    }
  }, []);

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

  async function runQualify() {
    if (!token || !qualifySource.trim()) return;
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
        { source: qualifySource.trim() },
        { headers: { "X-Admin-Token": token } },
      );
      setQualifyPreview(preview);
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
        { stars_override: overrides },
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
        { ss_leaderboard_ids: {}, reviewer: "staff" },
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

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-black tracking-tight">Administração</h1>
        <p className="mt-1 text-sm text-muted">
          Fila de reweight e execução manual do batch semanal.
        </p>
      </div>

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

      {/* Fila de reweight */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Sugestões de reweight (pendentes)</CardTitle>
          {token ? (
            <Button variant="ghost" size="sm" onClick={() => loadSuggestions(token)}>
              Recarregar
            </Button>
          ) : null}
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
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
        </CardContent>
      </Card>

      {/* Qualificação de mapas (nova batch) */}
      <Card>
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

              <div className="overflow-hidden rounded-lg border border-border-subtle">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border-subtle bg-surface text-left text-xs uppercase tracking-wider text-muted">
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
                    {qualifyPreview.difficulties.map((d) => (
                      <tr key={d.id} className="border-b border-border-subtle/60 last:border-b-0">
                        <td className="px-4 py-2 font-medium">{d.name}</td>
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
                    ))}
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
                  Edite o campo Stars para pedir ao ML um ajuste manual do nível.
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
            <div className="overflow-hidden rounded-lg border border-border-subtle">
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
                  {candidates.map((cand) => (
                    <tr key={cand.id} className="border-b border-border-subtle/60 last:border-b-0">
                      <td className="px-4 py-2.5 font-medium">
                        <div className="flex flex-col gap-0.5">
                          <span className="truncate">{cand.name}</span>
                          <span className="text-xs text-muted">{cand.mapper ?? "—"}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant={cand.status === "qualified" ? "secondary" : "warning"}>
                          {cand.status === "qualified" ? "na fila" : "candidato"}
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
                          ) : (
                            <Button
                              size="sm"
                              onClick={() => runQueueFor(cand.id)}
                              disabled={!token || queueLoading}
                            >
                              {queueLoading ? <Spinner size={12} /> : null}
                              Colocar na fila
                            </Button>
                          )}
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
                        </div>
                      </td>
                    </tr>
                  ))}
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
            <div className="overflow-hidden rounded-lg border border-border-subtle">
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
  );
}
