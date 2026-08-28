"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";
import { Spinner } from "@/components/ui/spinner";

const OPTIONS = [
  { value: "stars", label: "Mais estrelas" },
  { value: "recent", label: "Recentes" },
  { value: "name", label: "Nome (A–Z)" },
] as const;

/** Dropdown de ordenação dos mapas; atualiza ?sort= e volta para a página 1. */
export function SortSelect({ value }: { value: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pending, startTransition] = useTransition();

  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      Ordenar por
      <span className="relative inline-flex items-center">
        <select
          value={value}
          onChange={(event) => {
            const next = new URLSearchParams(searchParams.toString());
            next.set("sort", event.target.value);
            next.delete("page");
            startTransition(() => router.push(`${pathname}?${next.toString()}`));
          }}
          className="h-9 appearance-none rounded-md border border-border-subtle bg-surface pl-3 pr-8 text-sm font-medium text-foreground focus:border-secondary focus:outline-none"
        >
          {OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="pointer-events-none absolute right-2.5 h-4 w-4 text-muted"
          fill="currentColor"
        >
          <path d="M5.5 7.5 10 12l4.5-4.5H5.5Z" />
        </svg>
        {pending ? (
          <span className="absolute -right-5">
            <Spinner size={14} />
          </span>
        ) : null}
      </span>
    </label>
  );
}
