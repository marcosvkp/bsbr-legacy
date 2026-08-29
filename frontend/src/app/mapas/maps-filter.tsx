"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { Spinner } from "@/components/ui/spinner";

const STAR_MAX = 15;
const STAR_STEP = 0.5;

interface MapsFilterProps {
  initialQuery: string;
  minStars: number;
}

function formatStars(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(".", ",");
}

/** Busca por texto (nome/mapper) + slider de mínimo de estrelas; atualiza a URL (?q=&min_stars=). */
export function MapsFilter({ initialQuery, minStars }: MapsFilterProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(initialQuery);
  const [pending, startTransition] = useTransition();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sincroniza quando a URL muda por navegação externa (voltar do navegador, links).
  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    next.delete("page");
    startTransition(() => router.push(`${pathname}?${next.toString()}`));
  };

  const onQueryInput = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const trimmed = value.trim();
      update({ q: trimmed === "" ? null : trimmed });
    }, 300);
  };

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <label className="relative flex flex-1 items-center">
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="pointer-events-none absolute left-3 h-4 w-4 text-muted"
        >
          <path
            fillRule="evenodd"
            d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"
            clipRule="evenodd"
          />
        </svg>
        <input
          type="search"
          value={query}
          onChange={(event) => onQueryInput(event.target.value)}
          placeholder="Buscar por nome do mapa ou mapper…"
          aria-label="Buscar mapa"
          className="h-9 w-full rounded-md border border-border-subtle bg-surface pl-9 pr-8 text-sm text-foreground placeholder:text-muted focus:border-secondary focus:outline-none"
        />
        {pending ? (
          <span className="absolute right-3">
            <Spinner size={14} />
          </span>
        ) : query ? (
          <button
            type="button"
            aria-label="Limpar busca"
            onClick={() => onQueryInput("")}
            className="absolute right-3 text-muted transition-colors hover:text-foreground"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        ) : null}
      </label>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-muted">
          <span className="whitespace-nowrap font-semibold">
            {minStars > 0 ? `≥ ${formatStars(minStars)}★` : "Todas as estrelas"}
          </span>
          <input
            type="range"
            min={0}
            max={STAR_MAX}
            step={STAR_STEP}
            value={minStars}
            onChange={(event) => {
              const value = Number(event.target.value);
              update({ min_stars: value > 0 ? String(value) : null });
            }}
            aria-label="Filtrar por mínimo de estrelas"
            className="h-1.5 w-36 cursor-pointer appearance-none rounded-full bg-surface-2 accent-[var(--secondary)]"
          />
        </label>
      </div>
    </div>
  );
}
