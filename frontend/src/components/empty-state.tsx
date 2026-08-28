import { API_BASE } from "@/lib/api";
import { Card } from "@/components/ui/card";

function EmptyIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="text-muted/50"
    >
      <ellipse cx="12" cy="6" rx="8" ry="3" />
      <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6" />
      <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
    </svg>
  );
}

export interface EmptyStateProps {
  title: string;
  description?: string;
}

/** Estado vazio genérico: título + descrição, centralizado num cartão. */
export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <EmptyIcon />
      <p className="text-base font-semibold">{title}</p>
      {description ? (
        <p className="max-w-md text-sm text-muted">{description}</p>
      ) : null}
    </Card>
  );
}

export interface BackendOfflineProps {
  what: string;
}

/** Estado vazio quando a API está fora do ar (fetch falhou em página server-side). */
export function BackendOffline({ what }: BackendOfflineProps) {
  return (
    <EmptyState
      title="Backend indisponível"
      description={`Não foi possível carregar ${what}. Verifique se a API está rodando em ${API_BASE} e recarregue a página.`}
    />
  );
}
