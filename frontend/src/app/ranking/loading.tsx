import { Spinner } from "@/components/ui/spinner";

export default function Loading() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-muted">
      <Spinner size={28} />
      <p className="text-sm">Carregando ranking…</p>
    </div>
  );
}
