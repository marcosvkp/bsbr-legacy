"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { ApiError, getJson, postJson } from "@/lib/api";
import type {
  AdminSuggestion,
  AdminSuggestionsResponse,
  MapSuggestionActionResponse,
} from "@/lib/types";
import { formatDateTime, formatInt } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Pagination } from "@/components/pagination";
import { PlayerAvatar } from "@/components/player-avatar";
import { SmartImg } from "@/components/smart-img";

const PAGE_SIZE = 12;

const STATUS_VARIANT: Record<string, "warning" | "secondary" | "default"> = {
  pending: "warning",
  approved: "secondary",
  rejected: "default",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente",
  approved: "Aprovada",
  rejected: "Recusada",
};

/** Revisão de sugestões de mapas da comunidade — cards paginados. */
export function SuggestionsSection({ token }: { token: string | null }) {
  const searchParams = useSearchParams();
  const page = Math.max(1, Number.parseInt(searchParams.get("page") ?? "1", 10) || 1);

  const [data, setData] = useState<AdminSuggestionsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<number | null>(null);

  const load = useCallback(async (activeToken: string, targetPage: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getJson<AdminSuggestionsResponse>(
        `/admin/suggestions?limit=${PAGE_SIZE}&offset=${(targetPage - 1) * PAGE_SIZE}`,
        { headers: { "X-Admin-Token": activeToken } },
      );
      setData(res);
    } catch (cause) {
      setData(null);
      setError(
        cause instanceof ApiError && cause.status === 403
          ? "Token inválido (403)."
          : cause instanceof ApiError
            ? cause.message
            : "Falha de rede ao carregar sugestões.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) void load(token, page);
  }, [token, page, load]);

  const act = useCallback(
    async (id: number, action: "approve" | "reject") => {
      if (!token) return;
      setActingId(id);
      setError(null);
      try {
        await postJson<MapSuggestionActionResponse>(
          `/admin/suggestions/${id}/${action}`,
          {},
          { headers: { "X-Admin-Token": token } },
        );
        await load(token, page);
      } catch (cause) {
        setError(
          cause instanceof ApiError && cause.status === 403
            ? "Token inválido (403)."
            : cause instanceof ApiError
              ? cause.message
              : "Falha de rede na ação.",
        );
      } finally {
        setActingId(null);
      }
    },
    [token, page, load],
  );

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Sugestões de mapas da comunidade</CardTitle>
        {token ? (
          <Button variant="ghost" size="sm" onClick={() => load(token, page)}>
            Recarregar
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!token ? (
          <p className="py-4 text-sm text-muted">
            Informe o X-Admin-Token acima para revisar as sugestões.
          </p>
        ) : loading && !data ? (
          <div className="flex items-center justify-center gap-3 py-8 text-muted">
            <Spinner size={20} />
            <span className="text-sm">Carregando sugestões…</span>
          </div>
        ) : error ? (
          <p role="alert" className="py-4 text-sm font-medium text-danger">
            {error}
          </p>
        ) : data && data.items.length === 0 ? (
          <p className="py-4 text-sm text-muted">
            Nenhuma sugestão de mapa por aqui. Os jogadores logados enviam pela página /mapas.
          </p>
        ) : data ? (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {data.items.map((s: AdminSuggestion) => (
                <div
                  key={s.id}
                  className="flex flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm"
                >
                  <div className="relative">
                    <SmartImg
                      src={s.cover_url}
                      alt={`Capa de ${s.name}`}
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
                    <Badge
                      variant={STATUS_VARIANT[s.status]}
                      className="absolute right-2 top-2 backdrop-blur-sm"
                    >
                      {STATUS_LABEL[s.status]}
                    </Badge>
                  </div>
                  <div className="flex flex-1 flex-col gap-1.5 p-3.5">
                    <h3 className="line-clamp-2 text-[15px] font-bold leading-snug tracking-tight text-foreground">
                      {s.name}
                    </h3>
                    <p className="truncate text-xs text-muted">
                      {s.mapper ?? "Mapper desconhecido"}
                      {s.bpm != null ? (
                        <>
                          <span className="mx-1.5 text-muted/50">·</span>
                          {formatInt(s.bpm)} BPM
                        </>
                      ) : null}
                    </p>
                    <div className="flex items-center gap-1.5 text-xs text-muted">
                      <PlayerAvatar name={s.player_name ?? "?"} avatarUrl={s.player_avatar} size={18} />
                      <span className="truncate">{s.player_name ?? s.ss_id}</span>
                      <span className="text-muted/50">·</span>
                      <span className="shrink-0">{formatDateTime(s.created_at)}</span>
                    </div>
                    {s.note ? (
                      <p className="rounded-md bg-background/40 px-2 py-1.5 text-xs text-muted">
                        {s.note}
                      </p>
                    ) : null}
                    {s.status === "pending" ? (
                      <div className="mt-auto flex gap-2 pt-2">
                        <Button
                          size="sm"
                          onClick={() => act(s.id, "approve")}
                          disabled={actingId !== null}
                        >
                          {actingId === s.id ? <Spinner size={12} /> : null}
                          Aprovar
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => act(s.id, "reject")}
                          disabled={actingId !== null}
                        >
                          Recusar
                        </Button>
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
            {data.total > 0 ? (
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={data.total}
                basePath="/admin"
                params={{ tab: "suggestions" }}
              />
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
