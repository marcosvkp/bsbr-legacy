"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { API_BASE, ApiError, deleteJson, getJson, postJson } from "@/lib/api";
import { AdminTabs, type AdminTab } from "./admin-tabs";
import { ReweightCatalog } from "./reweight-catalog";
import { SuggestionsSection } from "./suggestions-section";
import { WebhooksSection } from "./webhooks-section";
import type {
  AdminBatchItem,
  AdminBatchesResponse,
  AdminCandidate,
  AdminMeResponse,
  AdminRankedMap,
  AdminStaffResponse,
  BatchStats,
  QualifyPreviewResponse,
  StaffMember,
} from "@/lib/types";
import { formatDateTime, formatInt, formatNumber } from "@/lib/format";
import { SmartImg } from "@/components/smart-img";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

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

function SteamLoginButton() {
  return (
    <a
      href={`${API_BASE}/auth/steam/login`}
      className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white transition-colors hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      Entrar com Steam
    </a>
  );
}

function AdminDashboard() {
  const [me, setMe] = useState<AdminMeResponse | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authStatus, setAuthStatus] = useState<
    "ok" | "anonymous" | "forbidden" | "error" | null
  >(null);

  const [batches, setBatches] = useState<AdminBatchItem[] | null>(null);
  const [batchesError, setBatchesError] = useState<string | null>(null);

  const [batchStats, setBatchStats] = useState<BatchStats | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);

  // Qualificação de mapas (nova batch)
  const [qualifySource, setQualifySource] = useState("");
  const [qualifyPreview, setQualifyPreview] = useState<QualifyPreviewResponse | null>(null);
  const [qualifyLoading, setQualifyLoading] = useState(false);
  const [qualifyError, setQualifyError] = useState<string | null>(null);
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

  // Equipe (staff) — owner
  const [staff, setStaff] = useState<StaffMember[] | null>(null);
  const [staffInput, setStaffInput] = useState("");
  const [staffBusy, setStaffBusy] = useState(false);
  const [staffRemoving, setStaffRemoving] = useState<number | null>(null);
  const [staffError, setStaffError] = useState<string | null>(null);
  const [staffNotice, setStaffNotice] = useState<string | null>(null);

  const tab = (useSearchParams().get("tab") ?? "qualification") as AdminTab;

  const loadBatches = useCallback(async () => {
    setBatchesError(null);
    try {
      const data = await getJson<AdminBatchesResponse>("/admin/batches");
      setBatches(data.items);
    } catch (cause) {
      setBatches(null);
      setBatchesError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao carregar batches.",
      );
    }
  }, []);

  const loadCandidates = useCallback(async () => {
    setCandidatesError(null);
    try {
      const data = await getJson<{ items: AdminCandidate[] }>("/admin/maps/candidates");
      setCandidates(data.items);
      setExcludedByMap((prev) => {
        const next: Record<number, string[]> = { ...prev };
        for (const item of data.items) {
          next[item.id] = item.difficulties.filter((d) => !d.is_ranked).map((d) => d.name);
        }
        return next;
      });
    } catch (cause) {
      setCandidatesError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao carregar a fila.",
      );
    }
  }, []);

  const loadRankedMaps = useCallback(async (opts: { q?: string; offset?: number; append?: boolean } = {}) => {
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
      );
      setRankedMaps((prev) => (opts.append ? [...(prev ?? []), ...data.items] : data.items));
      setRankedTotal(data.total);
    } catch (cause) {
      setRankedError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao carregar mapas rankeados.",
      );
    } finally {
      setRankedLoading(false);
    }
  }, []);

  const loadStaff = useCallback(async () => {
    setStaffError(null);
    try {
      const data = await getJson<AdminStaffResponse>("/admin/staff");
      setStaff(data.items);
    } catch (cause) {
      setStaffError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao carregar a equipe.",
      );
    }
  }, []);

  const onRankedSearch = (value: string) => {
    setRankedQuery(value);
    if (rankedDebounceRef.current) clearTimeout(rankedDebounceRef.current);
    rankedDebounceRef.current = setTimeout(() => {
      void loadRankedMaps({ q: value });
    }, 300);
  };

  async function runBatch() {
    setBatchLoading(true);
    setBatchError(null);
    try {
      const stats = await postJson<BatchStats>("/admin/batch/run", {}, { timeoutMs: 90_000 });
      setBatchStats(stats);
      void loadBatches();
    } catch (cause) {
      setBatchStats(null);
      setBatchError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao rodar o batch.",
      );
    } finally {
      setBatchLoading(false);
    }
  }

  async function runQualifyWith(source: string) {
    if (!source.trim()) return;
    setQualifyLoading(true);
    setQualifyError(null);
    setQualifyPreview(null);
    setStarsOverride({});
    setQueueError(null);
    setQueueSuccess(null);
    try {
      const preview = await postJson<QualifyPreviewResponse>(
        "/admin/maps/qualify",
        { source: source.trim() },
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
      setQualifyError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao analisar o mapa.",
      );
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
    setQueueLoading(true);
    setQueueError(null);
    setQueueSuccess(null);
    try {
      const result = await postJson<{ id: number; status: string }>(
        `/admin/maps/${mapId}/qualify`,
        {},
      );
      setQueueSuccess(
        `Mapa #${result.id} colocado na fila de qualificação (status ${result.status}).`,
      );
      void loadCandidates();
    } catch (cause) {
      setQueueError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao colocar na fila.",
      );
    } finally {
      setQueueLoading(false);
    }
  }

  async function runQueue() {
    if (!qualifyPreview) return;
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
      );
      setQueueSuccess(
        `Mapa #${result.id} colocado na fila de qualificação (status ${result.status}).`,
      );
      void loadCandidates();
    } catch (cause) {
      setQueueError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao colocar na fila.",
      );
    } finally {
      setQueueLoading(false);
    }
  }

  async function runReject(mapId: number) {
    setRejectLoading(mapId);
    setRejectError(null);
    setApproveError(null);
    setApproveSuccess(null);
    try {
      const result = await postJson<{ id: number; status: string }>(
        `/admin/maps/${mapId}/reject`,
        {},
      );
      setApproveSuccess(`Mapa #${result.id} recusado (status ${result.status}).`);
      void loadCandidates();
    } catch (cause) {
      setRejectError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao recusar o mapa.",
      );
    } finally {
      setRejectLoading(null);
    }
  }

  async function runApprove(mapId: number) {
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
      );
      setApproveSuccess(
        `Mapa #${result.id} aprovado (status ${result.status}). Lembre de rodar o batch para sincronizar scores.`,
      );
      void loadCandidates();
    } catch (cause) {
      setApproveError(
        cause instanceof ApiError ? cause.message : "Falha de rede ao aprovar o mapa.",
      );
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
    setRankToggling({ mapId, diffId: diff.id });
    setApproveError(null);
    try {
      await postJson(`/admin/maps/${mapId}/difficulties/${diff.id}/rank`, { ranked });
      await loadCandidates();
      await loadRankedMaps({ q: rankedQuery });
    } catch (cause) {
      setApproveError(
        cause instanceof ApiError
          ? cause.message
          : "Falha de rede ao alterar a dificuldade.",
      );
    } finally {
      setRankToggling(null);
    }
  }

  async function handleLogout() {
    try {
      await postJson("/auth/logout", {});
    } catch {
      // Sem rede o cookie é apagado mesmo assim pelo Set-Cookie do backend.
    }
    window.location.reload();
  }

  async function runStaffAdd(event: React.FormEvent) {
    event.preventDefault();
    const ss_id = staffInput.trim();
    if (!ss_id) return;
    if (!/^\d{17}$/.test(ss_id)) {
      setStaffError("Steam ID inválido — são exatamente 17 dígitos.");
      return;
    }
    setStaffBusy(true);
    setStaffError(null);
    setStaffNotice(null);
    try {
      await postJson<StaffMember>("/admin/staff", { ss_id, role: "staff" });
      setStaffInput("");
      setStaffNotice(`ss_id ${ss_id} adicionado à equipe.`);
      void loadStaff();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setStaffError("Esse ss_id já faz parte da equipe.");
      } else if (cause instanceof ApiError && cause.status === 422) {
        setStaffError("ss_id inválido (deve ser o Steam ID de 17 dígitos).");
      } else {
        setStaffError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao adicionar.",
        );
      }
    } finally {
      setStaffBusy(false);
    }
  }

  // Gate de sessão Steam: /admin/me → 200 staff, 401 anônimo, 403 não-staff.
  useEffect(() => {
    const id = setTimeout(() => {
      getJson<AdminMeResponse>("/admin/me")
        .then((identity) => {
          setMe(identity);
          setAuthStatus("ok");
        })
        .catch((cause) => {
          setMe(null);
          if (cause instanceof ApiError && cause.status === 401) {
            setAuthStatus("anonymous");
          } else if (cause instanceof ApiError && cause.status === 403) {
            setAuthStatus("forbidden");
          } else {
            setAuthStatus("error");
          }
        })
        .finally(() => setAuthLoading(false));
    }, 0);
    return () => clearTimeout(id);
  }, []);

  // Depois do gate ok: carrega as abas uma vez, fora do caminho síncrono do
  // efeito (react-hooks/set-state-in-effect).
  useEffect(() => {
    if (!me) return;
    const id = setTimeout(() => {
      void loadBatches();
      void loadCandidates();
      void loadRankedMaps({});
      if (me.role === "owner") void loadStaff();
    }, 0);
    return () => clearTimeout(id);
  }, [me, loadBatches, loadCandidates, loadRankedMaps, loadStaff]);

  async function runStaffRemove(member: StaffMember) {
    if (!window.confirm(`Remover ${member.name ?? member.ss_id} da equipe?`)) return;
    setStaffRemoving(member.id);
    setStaffError(null);
    setStaffNotice(null);
    try {
      await deleteJson(`/admin/staff/${member.id}`);
      setStaffNotice(`${member.name ?? member.ss_id} removido da equipe.`);
      void loadStaff();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        setStaffError("Não é possível remover este membro (último owner ou você mesmo).");
      } else {
        setStaffError(
          cause instanceof ApiError ? cause.message : "Falha de rede ao remover.",
        );
      }
    } finally {
      setStaffRemoving(null);
    }
  }

  if (authLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-32 text-muted">
        <Spinner size={24} />
        <p className="text-sm">Verificando sua sessão de administrador…</p>
      </div>
    );
  }

  if (authStatus === "anonymous") {
    return (
      <div className="mx-auto mt-16 flex w-full max-w-md flex-col items-center gap-4 rounded-lg border border-border-subtle bg-surface p-8 text-center shadow-sm">
        <h1 className="text-xl font-black tracking-tight">Área administrativa</h1>
        <p className="text-sm text-muted">
          Entre com sua conta Steam para acessar o painel. Somente membros da
          equipe do BSBR têm permissão aqui.
        </p>
        <SteamLoginButton />
      </div>
    );
  }

  if (authStatus === "forbidden") {
    return (
      <div className="mx-auto mt-16 flex w-full max-w-md flex-col items-center gap-4 rounded-lg border border-border-subtle bg-surface p-8 text-center shadow-sm">
        <h1 className="text-xl font-black tracking-tight">Acesso restrito à equipe do BSBR</h1>
        <p className="text-sm text-muted">
          Sua conta Steam não faz parte da equipe do BSBR. Se você é da equipe,
          entre com a conta Steam cadastrada no painel.
        </p>
        <SteamLoginButton />
      </div>
    );
  }

  if (authStatus === "error" || !me) {
    return (
      <div className="mx-auto mt-16 flex w-full max-w-md flex-col items-center gap-4 rounded-lg border border-border-subtle bg-surface p-8 text-center shadow-sm">
        <h1 className="text-xl font-black tracking-tight">Falha ao verificar a sessão</h1>
        <p className="text-sm text-muted">
          Não foi possível confirmar seu acesso agora. Tente novamente em instantes.
        </p>
        <Button onClick={() => window.location.reload()}>Tentar novamente</Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Identidade do admin */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black tracking-tight">Administração</h1>
          <p className="mt-1 text-sm text-muted">
            Qualificação, sugestões da comunidade, reweight e batch semanal.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border-subtle bg-surface px-3 py-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
            {me.role === "owner" ? "Owner" : "Staff"}
          </span>
          <span className="text-sm font-semibold text-foreground">
            {me.name ?? me.ss_id}
          </span>
          <span className="font-mono text-xs text-muted">{me.ss_id}</span>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            Sair
          </Button>
        </div>
      </div>

      <AdminTabs active={tab} />

      {/* Equipe (staff) — somente owner */}
      {me.role === "owner" ? (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Equipe (staff)</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => loadStaff()}>
              Recarregar
            </Button>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <form onSubmit={runStaffAdd} className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                Steam ID (17 dígitos)
                <input
                  type="text"
                  inputMode="numeric"
                  value={staffInput}
                  onChange={(e) => setStaffInput(e.target.value)}
                  placeholder="76561198000000000"
                  autoComplete="off"
                  className="h-9 w-full max-w-xs rounded-md border border-border-subtle bg-background px-3 font-mono text-sm text-foreground placeholder:text-muted/60 focus:border-secondary focus:outline-none"
                />
              </label>
              <Button type="submit" disabled={staffBusy || !staffInput.trim()}>
                {staffBusy ? <Spinner size={14} /> : null}
                Adicionar
              </Button>
              <span className="text-xs text-muted">
                Adiciona como role &quot;staff&quot; (somente owner gerencia a equipe).
              </span>
            </form>
            {staffError ? (
              <p role="alert" className="text-sm text-danger">{staffError}</p>
            ) : null}
            {staffNotice ? (
              <p role="status" className="text-sm text-emerald-600">{staffNotice}</p>
            ) : null}
            {staff === null ? (
              <p className="text-sm text-muted">Carregando equipe…</p>
            ) : staff.length === 0 ? (
              <p className="text-sm text-muted">
                Nenhum membro além de você. Adicione o Steam ID dos staffs para liberar o painel.
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {staff.map((member) => (
                  <li
                    key={member.id}
                    className="flex flex-wrap items-center gap-3 rounded-lg border border-border-subtle bg-background/40 px-3 py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 text-sm">
                        <span className="truncate font-semibold">
                          {member.name ?? member.ss_id}
                        </span>
                        <Badge variant={member.role === "owner" ? "accent" : "secondary"}>
                          {member.role}
                        </Badge>
                        {member.ss_id === me.ss_id ? (
                          <Badge variant="default">você</Badge>
                        ) : null}
                      </p>
                      <p className="truncate font-mono text-xs text-muted">{member.ss_id}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={staffRemoving === member.id}
                      onClick={() => runStaffRemove(member)}
                      className="text-danger hover:text-danger"
                    >
                      {staffRemoving === member.id ? <Spinner size={12} /> : null}
                      Remover
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}

      <div hidden={tab !== "reweight"} className="flex flex-col gap-6">
        <ReweightCatalog />
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
                disabled={qualifyLoading}
                className="w-full max-w-sm rounded-md border border-border-subtle bg-background px-3 py-1.5 text-sm outline-none transition-colors focus:border-secondary sm:w-72"
              />
              <Button onClick={runQualify} disabled={qualifyLoading || !qualifySource.trim()}>
                {qualifyLoading ? <Spinner size={14} /> : null}
                Analisar com o ML
              </Button>
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
                    <span className="text-xs text-muted">
                      novo candidato (preview das predições do ML)
                    </span>
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
                                <span className="ml-2 text-xs font-semibold text-danger">
                                  fora do ranking
                                </span>
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
                                <span className="text-warning">
                                  não encontrado no ScoreSaber
                                </span>
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
                    disabled={queueLoading}
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
            <Button variant="ghost" size="sm" onClick={() => loadCandidates()}>
              Recarregar
            </Button>
          </CardHeader>
          <CardContent>
            {candidatesError ? (
              <p role="alert" className="py-4 text-sm text-danger">{candidatesError}</p>
            ) : candidates === null ? (
              <p className="py-4 text-sm text-muted">Carregando…</p>
            ) : candidates.length === 0 ? (
              <p className="py-4 text-sm text-muted">
                Nenhum candidato na fila. Analise um mapa acima para começar.
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {candidates.map((cand) => {
                  const isRankedMap = cand.status === "ranked";
                  const candExcluded = excludedByMap[cand.id] ?? [];
                  return (
                    <div
                      key={cand.id}
                      className="flex flex-col overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm"
                    >
                      {/* Cover + identidade */}
                      <div className="relative flex items-center gap-3 p-3 pb-0">
                        <SmartImg
                          src={cand.cover_url ?? ""}
                          alt=""
                          fallback=""
                          className="h-12 w-12 shrink-0 rounded-md object-cover"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="line-clamp-2 text-sm font-semibold leading-snug" title={cand.name}>
                            {cand.name}
                          </p>
                          <p className="mt-0.5 truncate text-xs text-muted">
                            {cand.mapper ?? "—"}
                            {cand.bpm ? ` · ${Math.round(cand.bpm)} BPM` : ""}
                          </p>
                        </div>
                      </div>

                      {/* Status + ações */}
                      <div className="flex flex-wrap items-center justify-between gap-2 p-3 pb-0">
                        <Badge
                          variant={cand.status === "ranked" ? "success" : cand.status === "qualified" ? "secondary" : "warning"}
                        >
                          {cand.status === "ranked"
                            ? "rankeado"
                            : cand.status === "qualified"
                              ? "na fila"
                              : "candidato"}
                        </Badge>
                        <div className="flex flex-wrap items-center gap-1.5">
                          {cand.status === "qualified" ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => runApprove(cand.id)}
                              disabled={approveLoading}
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
                                disabled={qualifyLoading}
                              >
                                {qualifyLoading ? <Spinner size={12} /> : null}
                                Analisar ML
                              </Button>
                              <Button
                                size="sm"
                                onClick={() => runQueueFor(cand.id)}
                                disabled={queueLoading}
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
                              disabled={rejectLoading === cand.id}
                              className="text-danger hover:text-danger"
                            >
                              {rejectLoading === cand.id ? <Spinner size={12} /> : null}
                              Recusar
                            </Button>
                          ) : null}
                        </div>
                      </div>

                      {/* Dificuldades */}
                      <div className="flex flex-wrap items-center gap-1.5 p-3">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-muted">
                          Diffs
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
                                    : "border-border-subtle bg-background text-foreground"
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
                    </div>
                  );
                })}
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
            {rankedLoading && !rankedMaps ? (
              <p className="flex items-center gap-2 text-sm text-muted">
                <Spinner size={14} /> carregando mapas rankeados…
              </p>
            ) : rankedError ? (
              <p role="alert" className="text-sm text-danger">{rankedError}</p>
            ) : !rankedMaps || rankedMaps.length === 0 ? (
              <p className="text-sm text-muted">
                {rankedQuery.trim()
                  ? "Nenhum mapa rankeado com essa busca."
                  : "Nenhum mapa rankeado."}
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
                            const toggling =
                              rankToggling?.mapId === m.id && rankToggling?.diffId === d.id;
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
                      void loadRankedMaps({
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
              <Button onClick={runBatch} disabled={batchLoading}>
                {batchLoading ? <Spinner size={14} /> : null}
                Rodar batch agora
              </Button>
              {batchLoading ? (
                <span className="text-sm text-muted">
                  Executando pipeline completa (sync → reweight → ranking → snapshot)…
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
            <Button variant="ghost" size="sm" onClick={() => loadBatches()}>
              Recarregar
            </Button>
          </CardHeader>
          <CardContent>
            {batchesError ? (
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

      {tab === "suggestions" ? <SuggestionsSection /> : null}
      {tab === "webhooks" ? <WebhooksSection /> : null}
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
