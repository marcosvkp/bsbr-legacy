import { formatPp } from "@/lib/format";
import { COMPONENT_META, type SubComponentKey } from "@/components/pp-meta";

export interface SubStatsProps {
  acc?: number | null;
  tech?: number | null;
  speed?: number | null;
  /** Formatação do valor (padrão: PP com 2 casas). */
  format?: (value: number | null | undefined) => string;
  size?: "sm" | "md";
}

const ORDER: readonly SubComponentKey[] = ["acc", "tech", "speed"];

/**
 * Decomposição ACC/TECH/SPEED em colunas de verdade (não texto corrido):
 * cada componente ganha uma célula com label, valor e barra de share.
 */
export function SubStats({ acc, tech, speed, format = formatPp, size = "md" }: SubStatsProps) {
  const values: Record<SubComponentKey, number | null | undefined> = { acc, tech, speed };
  const sum = ORDER.reduce((total, key) => total + Math.max(values[key] ?? 0, 0), 0);
  const barHeight = size === "sm" ? "h-0.5" : "h-1";

  return (
    <div className="grid w-full grid-cols-3 gap-1.5">
      {ORDER.map((key) => {
        const meta = COMPONENT_META[key];
        const value = values[key];
        const share = sum > 0 && (value ?? 0) > 0 ? (Math.max(value ?? 0, 0) / sum) * 100 : 0;
        return (
          <div
            key={key}
            className={`flex flex-col gap-0.5 rounded-md border px-2 py-1 ${meta.cell} ${meta.border}`}
          >
            <span className={`text-[9px] font-bold uppercase tracking-widest ${meta.text}`}>
              {meta.label}
            </span>
            <span
              className={`text-[13px] font-bold tabular-nums ${
                size === "sm" ? "text-xs" : ""
              }`}
            >
              {format(value)}
            </span>
            <span className={`${barHeight} w-full overflow-hidden rounded-full bg-background/60`}>
              <span
                className={`block h-full rounded-full ${meta.bar}`}
                style={{ width: `${share}%`, opacity: value ? 0.85 : 0.15 }}
              />
            </span>
          </div>
        );
      })}
    </div>
  );
}
