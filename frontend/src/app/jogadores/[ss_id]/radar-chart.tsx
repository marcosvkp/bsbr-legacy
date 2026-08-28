import { formatPp } from "@/lib/format";
import { COMPONENT_META, type SubComponentKey } from "@/components/pp-meta";

export interface RadarChartProps {
  /** pp do jogador por componente. */
  player: Record<SubComponentKey, number | null>;
  /** pp do líder de cada componente (normalização). */
  leader: Record<SubComponentKey, number | null>;
}

const SIZE = 340;
const CENTER = { x: SIZE / 2, y: 168 };
const RADIUS = 112;
const AXES: SubComponentKey[] = ["acc", "tech", "speed"];
const RINGS = [0.25, 0.5, 0.75, 1];

function axisPoint(key: SubComponentKey, value: number): { x: number; y: number } {
  const index = AXES.indexOf(key);
  const angle = ((-90 + index * 120) * Math.PI) / 180;
  return {
    x: CENTER.x + RADIUS * value * Math.cos(angle),
    y: CENTER.y + RADIUS * value * Math.sin(angle),
  };
}

function polygon(values: number[]): string {
  return values
    .map((value, index) => {
      const angle = ((-90 + index * 120) * Math.PI) / 180;
      const x = CENTER.x + RADIUS * value * Math.cos(angle);
      const y = CENTER.y + RADIUS * value * Math.sin(angle);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

const LABEL_POS: Record<SubComponentKey, { x: number; y: number }> = {
  acc: { x: CENTER.x, y: CENTER.y - RADIUS - 26 },
  tech: { x: CENTER.x - RADIUS * 0.866, y: CENTER.y + RADIUS * 0.5 + 22 },
  speed: { x: CENTER.x + RADIUS * 0.866, y: CENTER.y + RADIUS * 0.5 + 22 },
};

/** Radar SVG puro dos 3 componentes de PP, normalizados contra o líder do ranking. */
export function RadarChart({ player, leader }: RadarChartProps) {
  const ratios = AXES.map((key) => {
    const mine = player[key] ?? 0;
    const top = leader[key] ?? 0;
    if (top <= 0 || mine <= 0) return 0;
    return Math.min(mine / top, 1);
  });

  const labelLines = AXES.map((key) => ({
    key,
    mine: formatPp(player[key]),
    top: formatPp(leader[key]),
  }));

  return (
    <figure className="flex flex-col items-center">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label="Radar dos componentes de PP comparados ao líder"
        className="w-full max-w-sm"
      >
        {/* Anéis */}
        {RINGS.map((ring) => (
          <polygon
            key={ring}
            points={polygon(RINGS.map(() => ring))}
            fill="none"
            stroke="currentColor"
            strokeWidth={ring === 1 ? 1.2 : 0.6}
            className={ring === 1 ? "text-border-subtle" : "text-border-subtle/60"}
          />
        ))}
        {/* Eixos */}
        {AXES.map((key) => {
          const point = axisPoint(key, 1);
          return (
            <line
              key={key}
              x1={CENTER.x}
              y1={CENTER.y}
              x2={point.x}
              y2={point.y}
              stroke="currentColor"
              strokeWidth="0.6"
              className="text-border-subtle/60"
            />
          );
        })}
        {/* Polígono do jogador */}
        <polygon
          points={polygon(ratios)}
          fill="var(--accent)"
          fillOpacity="0.15"
          stroke="var(--accent)"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {AXES.map((key, index) => {
          const point = axisPoint(key, ratios[index]);
          return (
            <circle
              key={key}
              cx={point.x}
              cy={point.y}
              r="3.5"
              fill="var(--accent)"
            />
          );
        })}
        {/* Rótulos */}
        {labelLines.map(({ key, mine, top }) => {
          const pos = LABEL_POS[key];
          return (
            <text
              key={key}
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              fontSize="11"
              fontWeight="700"
              fill="currentColor"
              className="text-foreground"
            >
              {COMPONENT_META[key].label} {mine}
              <tspan
                x={pos.x}
                dy="13"
                fontSize="10"
                fontWeight="400"
                className="text-muted"
                fill="var(--muted)"
              >
                líder {top}
              </tspan>
            </text>
          );
        })}
      </svg>
      <figcaption className="sr-only">
        Comparação dos PPs de acc, tech e speed com os líderes de cada componente.
      </figcaption>
    </figure>
  );
}
