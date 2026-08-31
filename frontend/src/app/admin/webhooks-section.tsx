"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, deleteJson, getJson, patchJson, postJson } from "@/lib/api";
import type { WebhookConfig, WebhooksResponse } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

/** Configuração dos webhooks do Discord (notificações de reweight). */
export function WebhooksSection({ token }: { token: string | null }) {
  const [items, setItems] = useState<WebhookConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(
    async (activeToken: string) => {
      setLoading(true);
      setError(null);
      try {
        const res = await getJson<WebhooksResponse>("/admin/webhooks", {
          headers: { "X-Admin-Token": activeToken },
        });
        setItems(res.items);
      } catch (cause) {
        setError(
          cause instanceof ApiError && cause.status === 403
            ? "Token inválido (403)."
            : cause instanceof ApiError
              ? cause.message
              : "Falha de rede ao carregar webhooks.",
        );
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (token) void load(token);
  }, [token, load]);

  const add = useCallback(async () => {
    if (!token || !url.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await postJson<WebhookConfig>(
        "/admin/webhooks",
        { url: url.trim(), label: label.trim() || null },
        { headers: { "X-Admin-Token": token } },
      );
      setUrl("");
      setLabel("");
      await load(token);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 409
          ? "Esse webhook já está cadastrado."
          : cause instanceof ApiError && cause.status === 422
            ? "URL inválida — precisa começar com http(s)."
            : cause instanceof ApiError
              ? cause.message
              : "Falha de rede ao adicionar.",
      );
    } finally {
      setSaving(false);
    }
  }, [token, url, label, load]);

  const toggle = useCallback(
    async (w: WebhookConfig) => {
      if (!token) return;
      setError(null);
      try {
        await patchJson<WebhookConfig>(
          `/admin/webhooks/${w.id}`,
          { enabled: !w.enabled },
          { headers: { "X-Admin-Token": token } },
        );
        await load(token);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : "Falha ao alternar.");
      }
    },
    [token, load],
  );

  const remove = useCallback(
    async (w: WebhookConfig) => {
      if (!token) return;
      if (!window.confirm(`Remover o webhook "${w.label ?? w.url}"?`)) return;
      setError(null);
      try {
        await deleteJson(`/admin/webhooks/${w.id}`, {
          headers: { "X-Admin-Token": token },
        });
        await load(token);
      } catch {
        setError("Falha ao remover.");
      }
    },
    [token, load],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Webhooks do Discord (notificações de reweight)</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted">
          Os reweights de mapas (estilo "Monthly Reweight") são enviados para esses endpoints.
          O relatório de sync/batch não vai para cá. Sem nenhum cadastrado, o backend usa o{" "}
          <code className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">DISCORD_WEBHOOK_URL</code>{" "}
          do ambiente.
        </p>

        {!token ? (
          <p className="text-sm text-muted">Informe o X-Admin-Token acima para gerenciar.</p>
        ) : (
          <>
            <div className="flex flex-col gap-2 rounded-lg border border-border-subtle bg-surface p-3 sm:flex-row">
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://discord.com/api/webhooks/..."
                aria-label="URL do webhook"
                className="h-9 flex-1 rounded-md border border-border-subtle bg-background px-3 text-sm text-foreground outline-none placeholder:text-muted/50 focus:border-secondary"
              />
              <input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Rótulo (ex.: Geral)"
                aria-label="Rótulo do webhook"
                className="h-9 w-full rounded-md border border-border-subtle bg-background px-3 text-sm text-foreground outline-none placeholder:text-muted/50 focus:border-secondary sm:w-40"
              />
              <Button size="sm" disabled={saving || !url.trim()} onClick={add}>
                {saving ? <Spinner size={12} /> : null}
                Adicionar
              </Button>
            </div>

            {error ? (
              <p role="alert" className="text-sm font-medium text-danger">
                {error}
              </p>
            ) : null}

            {loading && items.length === 0 ? (
              <div className="flex items-center justify-center gap-3 py-6 text-muted">
                <Spinner size={20} />
                <span className="text-sm">Carregando…</span>
              </div>
            ) : items.length === 0 ? (
              <p className="text-sm text-muted">
                Nenhum webhook cadastrado — as notificações usam o fallback do ambiente.
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {items.map((w) => (
                  <li
                    key={w.id}
                    className="flex items-center gap-3 rounded-lg border border-border-subtle bg-surface px-3 py-2.5"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                        <span className="truncate">{w.label ?? w.url}</span>
                        <Badge variant={w.enabled ? "success" : "warning"}>
                          {w.enabled ? "ativo" : "pausado"}
                        </Badge>
                      </p>
                      {w.label ? (
                        <p className="truncate text-xs text-muted">{w.url}</p>
                      ) : null}
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => toggle(w)}>
                      {w.enabled ? "Pausar" : "Ativar"}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => remove(w)}>
                      Remover
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
