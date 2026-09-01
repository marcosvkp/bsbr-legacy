"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getJson } from "@/lib/api";
import { formatPp } from "@/lib/format";
import type { PpHistoryPoint, PpHistoryResponse } from "@/lib/types";

const W = 640;
const H = 240;
const PAD = { left: 56, right: 40, top: 16, bottom: 30 };

const DAY_OPTIONS = [7, 30, 90, 180] as const;

function niceBounds(values: number[]): { min: number; max: number } {
  if (values.length === 0) return { min: 0, max: 1 };
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const span = rawMax - rawMin || rawMax || 1;
  return { min: rawMin - span * 0.1, max: rawMax + span * 0.1 };
}

function daysAgoLabel(nowMs: number, ts: string): string {
  const diffMs = nowMs - new Date(ts).getTime();
  const days = Math.round(diffMs / 86_400_000);
  if (days <= 0) return "hoje";
  return days === 1 ? "há 1 dia" : `há ${days} dias`;
}

function formatAxisPp(value: number): string {
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(value)}pp`;
}

interface PpHistoryChartProps {
  ssId: string;
  initial: PpHistoryResponse | null;
}

/**
 * Progressão de PP por timestamp dos scores: pontos reais (sólido) e amostras
 * estimadas em gaps sem dados (tracejado), com tooltip e handle "Agora".
 */
export function PpHistoryChart({ ssId, initial }: PpHistoryChartProps) {
  const [days, setDays] = useState<number>(initial?.days ?? 180);
  const [data, setData] = useState<PpHistoryResponse | null>(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [hover, setHover] = useState<number | null>(null);

  const load = useCallback(
    async (n: number) => {
      setLoading(true);
      setError(false);
      try {
        const next = await getJson<PpHistoryResponse>(`/players/${encodeURIComponent(ssId)}/pp-history?days=${n}`);
        setData(next);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    },
    [ssId],
  );

  useEffect(() => {
    if (initial?.days && initial.days !== days) {
      setDays(initial.days);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial?.days]);

  const changeDays = (n: number) => {
    setDays(n);
    void load(n);
  };

  const { points, nowMs } = useMemo(() => {
    const pts = data?.points ?? [];
    const now = data?.now ? new Date(data.now).getTime() : Date.now();
    return { points: pts, nowMs: now };
  }, [data]);

  const rendered = useMemo(() => {
    const t0 = points.length ? new Date(points[0].ts).getTime() : nowMs;
    const t1 = points.length > 1 ? new Date(points[points.length - 1].ts).getTime() : nowMs + 86_400_000;
    const span = t1 - t0 || 1;
    const plotW = W - PAD.left - PAD.right;
    const plotH = H - PAD.top - PAD.bottom;

    const values = points
      .map((p) => p.pp_total)
      .filter((v): v is number => v !== null && Number.isFinite(v));
    const bounds = niceBounds(values);
    const y = (value: number) =>
      PAD.top + (bounds.max - value) / (bounds.max - bounds.min || 1) * plotH;
    const x = (ts: string) => PAD.left + ((new Date(ts).getTime() - t0) / span) * plotW;

    const mapped: { x: number; y: number; estimated: boolean; pp: number | null; ts: string }[] = points.map(
      (p) => ({
        x: x(p.ts),
        y: p.pp_total !== null ? y(p.pp_total) : NaN,
        estimated: p.estimated,
        pp: p.pp_total,
        ts: p.ts,
      }),
    );

    // Polilinha única para a área de preenchimento (todos os pontos).
    const areaPath =
      mapped.length > 1
        ? `${mapped.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}`
        : "";

    // Separa em sub-caminhos sólido/tracejado por segmento (estimado = tracejado).
    // Cada run novo (troca de estilo) recomeça com M; dentro do run segue com L.
    let solidPath = "";
    let dashedPath = "";
    let prevStyle: "solid" | "dashed" | null = null;
    mapped.forEach((p, i) => {
      const style: "solid" | "dashed" =
        i === 0 ? "solid" : p.estimated || mapped[i - 1].estimated ? "dashed" : "solid";
      const startOfRun = prevStyle === null || style !== prevStyle;
      const cmd = `${startOfRun ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
      if (style === "solid") solidPath += cmd;
      else dashedPath += cmd;
      prevStyle = style;
    });

    const yTicks = [0, 1 / 3, 2 / 3, 1].map((t) => ({
      value: bounds.max - (bounds.max - bounds.min) * t,
      y: PAD.top + plotH * t,
    }));

    // 4 rótulos X: início, 1/3, 2/3, fim ("Agora").
    const xTicks = [0, 1 / 3, 2 / 3, 1]
      .map((t) => points[Math.min(points.length - 1, Math.round((points.length - 1) * t))])
      .filter(Boolean);

    return {
      bounds,
      y,
      mapped,
      areaPath,
      solidPath,
      dashedPath,
      yTicks,
      xTicks,
      empty: points.length === 0,
    };
  }, [points, nowMs]);

  const hovered = hover !== null ? rendered.mapped[hover] : null;
  const last = rendered.mapped[rendered.mapped.length - 1];

  return (
    <figure className="flex flex-col gap-2">
      {/* Seletor de janela */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-0.5 w-4 rounded-full bg-accent" />
            PP real
          </span>
          <span className="flex items-center gap-1.5">
            <svg aria-hidden="true" width="16" height="4">
              <line x1="0" y1="2" x2="16" y2="2" stroke="var(--accent)" strokeWidth="2" strokeDasharray="4 3" />
            </svg>
            estimado
          </span>
        </div>
        <div className="flex items-center gap-1">
          {DAY_OPTIONS.map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => changeDays(n)}
              disabled={loading}
              className={`rounded-md border px-2 py-1 text-xs font-semibold transition-colors disabled:opacity-50 ${
                days === n
                  ? "border-accent/50 bg-accent/10 text-accent"
                  : "border-border-subtle bg-surface text-muted hover:text-foreground"
              }`}
            >
              {n}d
            </button>
          ))}
        </div>
      </div>

      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Progressão de PP nos últimos ${days} dias`}
          className={`w-full transition-opacity ${loading ? "opacity-40" : ""}`}
        >
          {/* Grid + eixo Y (esquerda) */}
          {rendered.yTicks.map((tick) => (
            <g key={tick.y}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={tick.y}
                y2={tick.y}
                stroke="currentColor"
                strokeWidth="0.5"
                className="text-border-subtle/60"
              />
              <text x={PAD.left - 8} y={tick.y + 3} textAnchor="end" fontSize="10" fill="var(--muted)">
                {formatAxisPp(tick.value)}
              </text>
            </g>
          ))}
          {/* Rótulo do eixo Y */}
          <text
            transform={`translate(12, ${H / 2}) rotate(-90)`}
            textAnchor="middle"
            fontSize="10"
            fill="var(--accent)"
            letterSpacing="0.08em"
          >
            Pontos de Desempenho
          </text>

          {/* Rótulos X */}
          {rendered.xTicks.map((p, i) => (
            <text
              key={`${p.ts}-${i}`}
              x={rendered.mapped.find((m) => m.ts === p.ts)?.x ?? 0}
              y={H - 8}
              textAnchor={i === 0 ? "start" : i === rendered.xTicks.length - 1 ? "end" : "middle"}
              fontSize="10"
              fill="var(--muted)"
            >
              {i === rendered.xTicks.length - 1 ? "Agora" : daysAgoLabel(nowMs, p.ts)}
            </text>
          ))}

          {/* Área (todos os pontos) */}
          {rendered.areaPath ? (
            <path
              d={`${rendered.areaPath}L${rendered.mapped[rendered.mapped.length - 1].x.toFixed(1)},${H - PAD.bottom}L${rendered.mapped[0].x.toFixed(1)},${H - PAD.bottom}Z`}
              fill="var(--accent)"
              fillOpacity="0.08"
            />
          ) : null}

          {/* Linhas: sólida (real) + tracejada (estimado) */}
          {rendered.solidPath ? (
            <path
              d={rendered.solidPath}
              fill="none"
              stroke="var(--accent)"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}
          {rendered.dashedPath ? (
            <path
              d={rendered.dashedPath}
              fill="none"
              stroke="var(--accent)"
              strokeWidth="2"
              strokeDasharray="6 5"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}

          {/* Marcadores + hit areas do tooltip */}
          {rendered.mapped.map((p, i) => {
            if (!Number.isFinite(p.y)) return null;
            return (
              <g key={`pt-${i}`}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r="9"
                  fill="transparent"
                  className="cursor-pointer"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.estimated ? 2.5 : 3}
                  fill={p.estimated ? "var(--surface)" : "var(--accent)"}
                  stroke="var(--accent)"
                  strokeWidth={p.estimated ? 1 : 0}
                  pointerEvents="none"
                />
              </g>
            );
          })}

          {/* Handle "Agora" (ponto final) */}
          {last && Number.isFinite(last.y) ? (
            <g pointerEvents="none">
              <circle cx={last.x} cy={last.y} r="6.5" fill="var(--accent)" />
              <path
                d={`M${last.x + 1.5},${last.y - 3} L${last.x + 4.5},${last.y} L${last.x + 1.5},${last.y + 3} Z`}
                fill="white"
              />
            </g>
          ) : null}

          {rendered.empty ? (
            <text x={W / 2} y={H / 2} textAnchor="middle" fontSize="12" fill="var(--muted)">
              Sem scores rankeados no período
            </text>
          ) : null}
        </svg>

        {/* Tooltip */}
        {hovered && Number.isFinite(hovered.y) ? (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border border-border-subtle bg-surface-2 px-2.5 py-1.5 text-xs shadow-lg"
            style={{
              left: `${(hovered.x / W) * 100}%`,
              top: `${(hovered.y / H) * 100}%`,
            }}
          >
            <span className="flex items-center gap-1.5 whitespace-nowrap text-muted">
              <span aria-hidden="true" className="h-2 w-2 rounded-sm bg-accent" />
              {daysAgoLabel(nowMs, hovered.ts)}
            </span>
            <span className="whitespace-nowrap font-semibold tabular-nums">
              PP: {formatPp(hovered.pp)}pp{hovered.estimated ? " (estimado)" : ""}
            </span>
          </div>
        ) : null}
      </div>

      {error ? (
        <p className="text-xs text-danger">
          Não foi possível carregar a progressão. Clique em outra janela para tentar de novo.
        </p>
      ) : null}

      <figcaption className="sr-only">
        Progressão do PP total do jogador nos últimos {days} dias; segmentos tracejados são estimados.
      </figcaption>
    </figure>
  );
}
