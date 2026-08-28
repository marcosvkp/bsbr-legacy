import type { PlayerHistoryPoint } from "@/lib/types";
import { formatPp } from "@/lib/format";

export interface EvolutionChartProps {
  history: PlayerHistoryPoint[];
}

const W = 640;
const H = 240;
const PAD = { left: 52, right: 56, top: 16, bottom: 30 };

function niceBounds(values: number[]): { min: number; max: number } {
  if (values.length === 0) return { min: 0, max: 1 };
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const span = rawMax - rawMin || rawMax || 1;
  return { min: rawMin - span * 0.1, max: rawMax + span * 0.1 };
}

function scale(value: number, min: number, max: number, from: number, to: number): number {
  const t = (value - min) / (max - min || 1);
  return to - t * (to - from);
}

/**
 * Gráfico de linha SVG puro: PP total (sólido) e rank por semana (tracejado,
 * escala própria — melhor rank no topo).
 */
export function EvolutionChart({ history }: EvolutionChartProps) {
  const ppPoints = history
    .map((point, index) => ({ value: point.pp_total, index }))
    .filter((point): point is { value: number; index: number } => point.value !== null);
  const rankPoints = history
    .map((point, index) => ({ value: point.rank, index }))
    .filter((point): point is { value: number; index: number } => point.value !== null);

  const n = history.length;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (index: number) =>
    PAD.left + (n <= 1 ? plotW / 2 : (index * plotW) / (n - 1));

  const ppBounds = niceBounds(ppPoints.map((point) => point.value));
  const rankBounds = niceBounds(rankPoints.map((point) => point.value));
  const yPp = (value: number) => scale(value, ppBounds.min, ppBounds.max, H - PAD.bottom, PAD.top);
  // Rank: melhor (menor número) no topo.
  const yRank = (value: number) =>
    scale(value, rankBounds.min, rankBounds.max, H - PAD.bottom, PAD.top);

  const ppPath = ppPoints
    .map((point, i) => `${i === 0 ? "M" : "L"}${x(point.index).toFixed(1)},${yPp(point.value).toFixed(1)}`)
    .join(" ");
  const areaPath =
    ppPoints.length > 1
      ? `${ppPath}L${x(ppPoints[ppPoints.length - 1].index).toFixed(1)},${H - PAD.bottom}L${x(ppPoints[0].index).toFixed(1)},${H - PAD.bottom}Z`
      : "";
  const rankPath = rankPoints
    .map((point, i) => `${i === 0 ? "M" : "L"}${x(point.index).toFixed(1)},${yRank(point.value).toFixed(1)}`)
    .join(" ");

  const ppTicks = [0, 1 / 3, 2 / 3, 1].map((t) => {
    const value = ppBounds.min + (ppBounds.max - ppBounds.min) * t;
    return { value, y: PAD.top + plotH * t };
  });

  // history vazio (player sem snapshots ainda): sem rótulos de semana
  const xLabelIndexes = n === 0 ? [] : n <= 1 ? [0] : [0, Math.floor((n - 1) / 2), n - 1];

  return (
    <figure className="flex flex-col gap-2">
      <div className="flex items-center gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="h-0.5 w-4 rounded-full bg-accent" />
          PP total
        </span>
        <span className="flex items-center gap-1.5">
          <svg aria-hidden="true" width="16" height="4">
            <line x1="0" y1="2" x2="16" y2="2" stroke="var(--secondary)" strokeWidth="2" strokeDasharray="4 3" />
          </svg>
          Rank (melhor no topo)
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Evolução semanal de PP e rank"
        className="w-full"
      >
        {/* Grid + eixo PP (esquerda) */}
        {ppTicks.map((tick) => (
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
            <text
              x={PAD.left - 8}
              y={tick.y + 3}
              textAnchor="end"
              fontSize="10"
              fill="var(--muted)"
            >
              {formatPp(tick.value)}
            </text>
          </g>
        ))}
        {/* Eixo rank (direita) */}
        {[rankBounds.min, (rankBounds.min + rankBounds.max) / 2, rankBounds.max].map((value, i) => (
          <text
            key={i}
            x={W - PAD.right + 8}
            y={yRank(value) + 3}
            textAnchor="start"
            fontSize="10"
            fill="var(--secondary)"
          >
            #{Math.round(value)}
          </text>
        ))}
        {/* Rótulos X (semanas) */}
        {xLabelIndexes.map((index) => (
          <text
            key={index}
            x={x(index)}
            y={H - 8}
            textAnchor={index === 0 ? "start" : index === n - 1 ? "end" : "middle"}
            fontSize="10"
            fill="var(--muted)"
          >
            {history[index].week}
          </text>
        ))}
        {/* Área + linha PP */}
        {areaPath ? (
          <path d={areaPath} fill="var(--accent)" fillOpacity="0.08" />
        ) : null}
        {ppPoints.length > 1 ? (
          <path
            d={ppPath}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ) : null}
        {ppPoints.map((point) => (
          <circle
            key={`pp-${point.index}`}
            cx={x(point.index)}
            cy={yPp(point.value)}
            r="3"
            fill="var(--accent)"
          />
        ))}
        {/* Linha rank */}
        {rankPoints.length > 1 ? (
          <path
            d={rankPath}
            fill="none"
            stroke="var(--secondary)"
            strokeWidth="1.5"
            strokeDasharray="5 4"
            strokeLinejoin="round"
          />
        ) : null}
        {rankPoints.map((point) => (
          <circle
            key={`rank-${point.index}`}
            cx={x(point.index)}
            cy={yRank(point.value)}
            r="2.5"
            fill="var(--secondary)"
          />
        ))}
        {n === 0 ? (
          <text x={W / 2} y={H / 2} textAnchor="middle" fontSize="12" fill="var(--muted)">
            Sem histórico semanal
          </text>
        ) : null}
      </svg>
      <figcaption className="sr-only">
        Evolução do PP total e do rank do jogador ao longo das semanas.
      </figcaption>
    </figure>
  );
}
