/** Formatação pt-BR compartilhada (pp, acc %, datas, inteiros). */

const nf = (min: number, max: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: min, maximumFractionDigits: max });

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return nf(digits, digits).format(value);
}

/** PP com 2 casas (ex.: 1.234,56). */
export function formatPp(value: number | null | undefined): string {
  return formatNumber(value, 2);
}

/** Accuracy fracionária (0–1) → "97,88%". */
export function formatAcc(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${nf(1, 2).format(value * 100)}%`;
}

export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return nf(0, 0).format(value);
}

/** ISO string → "12/03/2026 14:30" (horário local). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("pt-BR", { dateStyle: "short" });
}
