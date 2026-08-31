"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { API_BASE, ApiError, getJson, postJson } from "@/lib/api";
import type { MapSuggestion, MeResponse, SuggestionsMeResponse } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SmartImg } from "@/components/smart-img";

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

/** Sugestão de mapas (login Steam) — botão na página /mapas. */
export function SuggestMap() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [checked, setChecked] = useState(false);
  const [my, setMy] = useState<SuggestionsMeResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMine = useCallback(async () => {
    try {
      setMy(await getJson<SuggestionsMeResponse>("/suggestions/me"));
    } catch {
      setMy(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    getJson<MeResponse>("/auth/me")
      .then(async (logged) => {
        if (cancelled) return;
        setMe(logged);
        await loadMine();
      })
      .catch(() => {
        if (!cancelled) setMe(null);
      })
      .finally(() => {
        if (!cancelled) setChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, [loadMine]);

  const login = useCallback(() => {
    window.location.assign(`${API_BASE}/auth/steam/login`);
  }, []);

  const openModal = useCallback(() => {
    setError(null);
    setSource("");
    setNote("");
    setOpen(true);
  }, []);

  const submit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      await postJson<MapSuggestion>(
        "/suggestions",
        { source, note: note.trim() || null },
        { timeoutMs: 30_000 }, // BeatSaver pode demorar
      );
      setOpen(false);
      await loadMine();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Sua sessão expirou. Entre novamente para sugerir.");
      } else if (err instanceof ApiError && typeof err.status === "number") {
        setError(err.message.replace(/^Resposta \d+ de .*?\/api\/v1/, ""));
      } else {
        setError("Falha ao enviar. Tente novamente em instantes.");
      }
    } finally {
      setSubmitting(false);
    }
  }, [source, note, loadMine]);

  const activeCount = my?.active_count ?? 0;
  const maxActive = my?.max_active ?? 3;

  return (
    <>
      {checked ? (
        me ? (
          <Button variant="secondary" size="sm" onClick={openModal}>
            Sugerir mapa
            <span className="text-muted">({activeCount}/{maxActive})</span>
          </Button>
        ) : (
          <Button variant="secondary" size="sm" onClick={login}>
            Entrar para sugerir
          </Button>
        )
      ) : (
        <div className="h-8 w-24 animate-pulse rounded-md bg-surface-2" aria-hidden="true" />
      )}

      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => !submitting && setOpen(false)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Sugerir mapa"
            className="relative z-10 flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
              <h2 className="font-display text-lg font-bold">Sugerir um mapa</h2>
              <button
                type="button"
                aria-label="Fechar"
                disabled={submitting}
                onClick={() => setOpen(false)}
                className="rounded-md px-2 py-1 text-muted hover:bg-surface-2 hover:text-foreground"
              >
                ✕
              </button>
            </div>

            <div className="flex flex-col gap-4 overflow-y-auto p-5">
              <p className="text-sm text-muted">
                Cola o link do BeatSaver (ou o ID/hash do mapa). O mapa entra na fila de
                qualificação — você pode ter até <strong className="text-foreground">{maxActive} ativas</strong>.
              </p>
              <Link
                href="/sobre#criteria"
                className="text-sm font-semibold text-secondary underline-offset-2 transition-colors hover:underline"
              >
                Antes de sugerir, confira os critérios de qualificação (Criteria Issues)
              </Link>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold uppercase tracking-wide text-muted">
                  Link do BeatSaver / ID / hash
                </span>
                <input
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  placeholder="https://beatsaver.com/maps/abc123"
                  disabled={submitting}
                  className="h-9 rounded-md border border-border-subtle bg-background px-3 text-sm text-foreground outline-none placeholder:text-muted/50 focus:border-secondary"
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold uppercase tracking-wide text-muted">
                  Comentário (opcional)
                </span>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={280}
                  rows={2}
                  disabled={submitting}
                  placeholder="Por que esse mapa merece entrar no ranking?"
                  className="resize-none rounded-md border border-border-subtle bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted/50 focus:border-secondary"
                />
              </label>

              {error ? (
                <p className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                  {error}
                </p>
              ) : null}

              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" disabled={submitting} onClick={() => setOpen(false)}>
                  Cancelar
                </Button>
                <Button size="sm" disabled={submitting || source.trim() === ""} onClick={submit}>
                  {submitting ? "Enviando…" : "Enviar sugestão"}
                </Button>
              </div>
            </div>

            {my && my.items.length > 0 ? (
              <div className="border-t border-border-subtle px-5 py-3.5">
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">
                  Minhas sugestões
                </h3>
                <ul className="flex flex-col gap-2">
                  {my.items.map((s) => (
                    <li key={s.id} className="flex items-center gap-3">
                      <SmartImg
                        src={s.cover_url}
                        alt={`Capa de ${s.name}`}
                        className="h-10 w-10 shrink-0 rounded-md bg-surface-2 object-cover"
                        fallback={
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-surface-2 text-muted/50" />
                        }
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">{s.name}</p>
                        <p className="truncate text-xs text-muted">
                          {s.mapper ?? "Mapper desconhecido"} · {formatDateTime(s.created_at)}
                        </p>
                      </div>
                      <Badge variant={STATUS_VARIANT[s.status]}>{STATUS_LABEL[s.status]}</Badge>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
