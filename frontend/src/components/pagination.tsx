import Link from "next/link";
import { formatInt } from "@/lib/format";

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  basePath: string;
  /** Query extras preservadas (ex.: component, sort). */
  params?: Record<string, string | undefined>;
}

export function buildHref(
  basePath: string,
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${basePath}?${query}` : basePath;
}

const LINK_CLASSES =
  "inline-flex h-8 items-center rounded-md border border-border-subtle bg-surface px-3 text-xs font-semibold transition-colors";
const LINK_ENABLED = `${LINK_CLASSES} text-foreground hover:bg-surface-2`;
const LINK_DISABLED = `${LINK_CLASSES} text-muted opacity-40`;

/** Paginação prev/next baseada em links (server-safe), com contagem "X–Y de Z". */
export function Pagination({ page, pageSize, total, basePath, params = {} }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <nav
      aria-label="Paginação"
      className="flex items-center justify-between gap-4 pt-2 text-sm text-muted"
    >
      <span aria-live="polite">
        Exibindo {formatInt(from)}–{formatInt(to)} de {formatInt(total)}
      </span>
      <div className="flex items-center gap-2">
        {page > 1 ? (
          <Link
            href={buildHref(basePath, { ...params, page: page - 1 })}
            className={LINK_ENABLED}
            aria-disabled="false"
          >
            Anterior
          </Link>
        ) : (
          <span className={LINK_DISABLED} aria-disabled="true">
            Anterior
          </span>
        )}
        <span className="tabular-nums">
          Página {formatInt(page)} de {formatInt(totalPages)}
        </span>
        {page < totalPages ? (
          <Link
            href={buildHref(basePath, { ...params, page: page + 1 })}
            className={LINK_ENABLED}
            aria-disabled="false"
          >
            Próxima
          </Link>
        ) : (
          <span className={LINK_DISABLED} aria-disabled="true">
            Próxima
          </span>
        )}
      </div>
    </nav>
  );
}
