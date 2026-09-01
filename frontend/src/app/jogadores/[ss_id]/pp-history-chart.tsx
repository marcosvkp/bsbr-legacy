"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getJson } from "@/lib/api";
import { formatPp } from "@/lib/format";
import type { PpHistoryResponse } from "@/lib/types";

const W = 680;
const H = 264;
const PAD = { left: 60, right: 48, top: 20, bottom: 34 };

const MONO = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";

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
 * Progressão de PP por timestamp dos scores.
 *
 * Direção visual: a essência é a dualidade real × estimado — a linha real
 * "acende" (gradiente) conforme se aproxima do presente; o passado sem dados
 * é um fantasma tracejado atenuado; o handle "Agora" é o pulso ao vivo.
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

    const mapped = points.map((p) => ({
      x: x(p.ts),
      y: p.pp_total !== null ? y(p.pp_total) : NaN,
      estimated: p.estimated,
      pp: p.pp_total,
      ts: p.ts,
    }));

    const areaPath =
      mapped.length > 1
        ? `${mapped.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}`
        : "";

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

  // Posiciona o tooltip sem estourar as bordas do gráfico.
  const tooltipPos = hovered
    ? {
        left: `${(hovered.x / W) * 100}%`,
        top: `${(hovered.y / H) * 100}%`,
        translateX: hovered.x < 64 ? "0%" : hovered.x > W - 64 ? "-100%" : "-50%",
      }
    : null;

  return (
    <figure className="flex flex-col gap-3">
      {/* Legenda + seletor de janela */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3 text-[11px] font-medium uppercase tracking-wider text-muted">
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-0.5 w-5 rounded-full bg-accent shadow-[0_0_6px_var(--accent)]" />
            Real
          </span>
          <span className="flex items-center gap-1.5">
            <svg aria-hidden="true" width="20" height="4" className="text-accent/60">
              <line x1="0" y1="2" x2="20" y2="2" stroke="currentColor" strokeWidth="2" strokeDasharray="5 3" strokeLinecap="round" />
            </svg>
            Estimado
          </span>
        </div>
        <div className="flex items-center gap-0.5 rounded-lg border border-border-subtle bg-surface p-0.5">
          {DAY_OPTIONS.map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => changeDays(n)}
              disabled={loading}
              aria-pressed={days === n}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold tabular-nums transition-colors disabled:opacity-50 ${
                days === n
                  ? "bg-accent/15 text-accent shadow-[inset_0_0_0_1px_rgba(239,68,68,0.35)]"
                  : "text-muted hover:text-foreground"
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
          className={`w-full transition-opacity duration-300 ${loading ? "opacity-40" : ""}`}
        >
          <defs>
            {/* Linha "acende" ao se aproximar do presente */}
            <linearGradient id="pp-line" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.45" />
              <stop offset="70%" stopColor="var(--accent)" stopOpacity="0.9" />
              <stop offset="100%" stopColor="var(--accent)" />
            </linearGradient>
            <linearGradient id="pp-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.16" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.02" />
            </linearGradient>
            <filter id="pp-glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Grid horizontal + ticks Y */}
          {rendered.yTicks.map((tick) => (
            <g key={tick.y}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={tick.y}
                y2={tick.y}
                stroke="currentColor"
                strokeWidth="0.5"
                className="text-border-subtle/50"
              />
              <text
                x={PAD.left - 10}
                y={tick.y + 3.5}
                textAnchor="end"
                fontSize="10.5"
                fill="var(--muted)"
                fontFamily={MONO}
              >
                {formatAxisPp(tick.value)}
              </text>
            </g>
          ))}

          {/* Rótulo do eixo Y */}
          <text
            transform={`translate(15, ${H / 2}) rotate(-90)`}
            textAnchor="middle"
            fontSize="10"
            fill="var(--muted)"
            letterSpacing="0.12em"
            style={{ textTransform: "uppercase" }}
          >
            Pontos de Desempenho
          </text>

          {/* Rótulos X (o último tick "Agora" é omitido — o PP atual já está no perfil). */}
          {rendered.xTicks.slice(0, -1).map((p, i) => {
            const pt = rendered.mapped.find((m) => m.ts === p.ts);
            if (!pt) return null;
            return (
              <text
                key={`${p.ts}-${i}`}
                x={pt.x}
                y={H - 10}
                textAnchor={i === 0 ? "start" : "middle"}
                fontSize="10.5"
                fill="var(--muted)"
                fontFamily={MONO}
              >
                {daysAgoLabel(nowMs, p.ts)}
              </text>
            );
          })}

          {/* Área preenchida (gradiente vertical) */}
          {rendered.areaPath ? (
            <path
              d={`${rendered.areaPath}L${rendered.mapped[rendered.mapped.length - 1].x.toFixed(1)},${H - PAD.bottom}L${rendered.mapped[0].x.toFixed(1)},${H - PAD.bottom}Z`}
              fill="url(#pp-area)"
            />
          ) : null}

          {/* Linha estimada (fantasma tracejado) */}
          {rendered.dashedPath ? (
            <path
              d={rendered.dashedPath}
              fill="none"
              stroke="var(--accent)"
              strokeOpacity="0.5"
              strokeWidth="2"
              strokeDasharray="5 6"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}

          {/* Linha real (sólida com gradiente + glow) */}
          {rendered.solidPath ? (
            <>
              <path
                d={rendered.solidPath}
                fill="none"
                stroke="var(--accent)"
                strokeOpacity="0.18"
                strokeWidth="6"
                strokeLinejoin="round"
                strokeLinecap="round"
                filter="url(#pp-glow)"
              />
              <path
                d={rendered.solidPath}
                fill="none"
                stroke="url(#pp-line)"
                strokeWidth="2.25"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </>
          ) : null}

          {/* Marcadores + hit areas */}
          {rendered.mapped.map((p, i) => {
            if (!Number.isFinite(p.y)) return null;
            return (
              <g key={`pt-${i}`}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r="10"
                  fill="transparent"
                  className="cursor-pointer"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.estimated ? 2.5 : 3.5}
                  fill={p.estimated ? "var(--surface-2)" : "var(--accent)"}
                  stroke={p.estimated ? "var(--accent)" : "var(--background)"}
                  strokeOpacity={p.estimated ? 0.5 : undefined}
                  strokeWidth={p.estimated ? 1 : 1.5}
                  opacity={p.estimated ? 0.75 : 1}
                  pointerEvents="none"
                />
              </g>
            );
          })}

          {/* Handle "Agora" omitido — o valor atual do PP já está visível no perfil. */}

          {rendered.empty ? (
            <g>
              <circle cx={W / 2} cy={H / 2 - 12} r="9" fill="none" stroke="var(--muted)" strokeWidth="1.5" />
              <path
                d={`M${W / 2 - 5},${H / 2 - 12} L${W / 2 + 5},${H / 2 - 12} M${W / 2},${H / 2 - 17} L${W / 2},${H / 2 - 7}`}
                stroke="var(--muted)"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
              <text x={W / 2} y={H / 2 + 14} textAnchor="middle" fontSize="12" fill="var(--muted)">
                Sem scores rankeados no período
              </text>
            </g>
          ) : null}
        </svg>

        {/* Tooltip com seta */}
        {hovered && Number.isFinite(hovered.y) && tooltipPos ? (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-10"
            style={{
              left: tooltipPos.left,
              top: tooltipPos.top,
              transform: `translate(${tooltipPos.translateX}, -100%) translateY(-10px)`,
            }}
          >
            <div className="rounded-lg border border-accent/25 bg-surface-2/95 px-3 py-2 shadow-[0_8px_24px_rgba(0,0,0,0.5)] backdrop-blur-sm">
              <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted">
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_5px_var(--accent)]" />
                {daysAgoLabel(nowMs, hovered.ts)}
              </div>
              <div className="mt-1 whitespace-nowrap font-mono text-sm font-semibold tabular-nums text-foreground">
                {formatPp(hovered.pp)}
                <span className="text-muted">pp</span>
                {hovered.estimated ? (
                  <span className="ml-1.5 text-[10px] font-medium uppercase tracking-wider text-accent/80">
                    estimado
                  </span>
                ) : null}
              </div>
            </div>
            <div className="mx-auto h-2 w-2 -translate-y-1 rotate-45 border-b border-r border-accent/25 bg-surface-2" />
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
