"use client";

import { useEffect, useRef, useState } from "react";
import type { LiveScoreItem } from "@/lib/types";

const WS_PATH = "/api/v1/ws/live";

function wsUrl(): string {
  const base = typeof window !== "undefined" ? window.location.origin : "";
  return base.replace(/^http/, "ws") + WS_PATH;
}

function liveKey(item: LiveScoreItem): string {
  return `${item.source}:${item.score_id}`;
}

export function LiveFeed({ initial }: { initial: LiveScoreItem[] }) {
  const [items, setItems] = useState<LiveScoreItem[]>(initial);
  const [connected, setConnected] = useState(false);
  const reconnectRef = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      const ws = new WebSocket(wsUrl());
      socketRef.current = ws;
      ws.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        reconnectRef.current = 0;
      };
      ws.onmessage = (event) => {
        try {
          const item = JSON.parse(event.data as string) as LiveScoreItem;
          setItems((prev) => {
            const next = [item, ...prev.filter((p) => liveKey(p) !== liveKey(item))];
            return next.slice(0, 30);
          });
        } catch {
          // mensagem malformada — ignora
        }
      };
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        const delay = Math.min(1000 * 2 ** reconnectRef.current, 15000);
        reconnectRef.current += 1;
        setTimeout(connect, delay);
      };
      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      cancelled = true;
      socketRef.current?.close();
    };
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-xs text-muted">
        <span className="relative inline-flex h-2 w-2" aria-hidden>
          <span
            className={`live-ping inline-block h-2 w-2 rounded-full ${
              connected ? "bg-emerald-500" : "bg-amber-500"
            }`}
          />
        </span>
        {connected ? "conectado — scores em tempo real" : "conectando…"}
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-muted">
          Nenhum score capturado ainda. O feed do ScoreSaber emite quando alguém
          joga um mapa rankeado — pode demorar alguns minutos fora dos horários de pico.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border-subtle">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle bg-surface text-left text-xs uppercase tracking-wider text-muted">
                <th scope="col" className="px-4 py-2.5 font-semibold">Jogador</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Mapa</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Diff</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">Score</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">Acc</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">PP</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={liveKey(item)} className="border-b border-border-subtle/60 last:border-b-0">
                  <td className="px-4 py-2.5 font-medium">
                    {item.player_name ?? item.player_id}
                    {item.full_combo ? (
                      <span className="ml-2 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-bold text-emerald-600">
                        FC
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2.5 text-muted">
                    {item.song_hash ? (
                      <a
                        href={`/mapas/${item.song_hash}`}
                        className="truncate font-mono text-xs hover:text-secondary"
                      >
                        {item.song_hash.slice(0, 8)}
                      </a>
                    ) : (
                      <span className="text-xs text-muted/60">lb {item.leaderboard_id}</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-muted">{item.difficulty ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {item.score.toLocaleString("pt-BR")}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-muted">
                    {item.acc != null ? `${(item.acc * 100).toFixed(2)}%` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right font-bold tabular-nums">
                    {item.pp != null ? item.pp.toFixed(1) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
