import type { Metadata } from "next";
import Link from "next/link";
import { getJson } from "@/lib/api";
import type { ComponentKey, RankingsResponse } from "@/lib/types";
import { isComponentKey } from "@/lib/types";
import { BackendOffline, EmptyState } from "@/components/empty-state";
import { Pagination } from "@/components/pagination";
import { RankingTable } from "./ranking-table";

export const metadata: Metadata = {
  title: "Ranking",
};

const TABS: Array<{ key: ComponentKey; label: string }> = [
  { key: "total", label: "Geral" },
  { key: "acc", label: "Acc" },
  { key: "tech", label: "Tech" },
  { key: "speed", label: "Speed" },
];

const PAGE_SIZE = 50;

function parsePage(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
}

export default async function RankingPage(props: PageProps<"/ranking">) {
  const searchParams = await props.searchParams;
  const componentParam = Array.isArray(searchParams.component)
    ? searchParams.component[0]
    : searchParams.component;
  const component: ComponentKey = isComponentKey(componentParam) ? componentParam : "total";
  const page = parsePage(Array.isArray(searchParams.page) ? searchParams.page[0] : searchParams.page);

  let data: RankingsResponse;
  try {
    data = await getJson<RankingsResponse>(
      `/rankings?component=${component}&page=${page}&page_size=${PAGE_SIZE}&country=BR`,
    );
  } catch {
    return <BackendOffline what="o ranking" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-black tracking-tight">Ranking brasileiro</h1>

        <div
          role="tablist"
          aria-label="Componente do ranking"
          className="flex w-fit gap-1 rounded-lg border border-border-subtle bg-surface p-1"
        >
          {TABS.map((tab) => {
            const active = tab.key === component;
            return (
              <Link
                key={tab.key}
                role="tab"
                aria-selected={active}
                href={`/ranking?component=${tab.key}`}
                className={`rounded-md px-4 py-1.5 text-sm font-semibold transition-colors ${
                  active
                    ? "bg-accent text-white"
                    : "text-muted hover:bg-surface-2 hover:text-foreground"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>
      </div>

      {data.items.length === 0 ? (
        <EmptyState
          title="Ranking vazio"
          description={
            page > 1
              ? "Esta página não tem jogadores. Volte para a primeira página."
              : "Ainda não há jogadores rankeados. O batch semanal popula o ranking."
          }
        />
      ) : (
        <>
          <RankingTable items={data.items} component={data.component} />
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            basePath="/ranking"
            params={{ component }}
          />
        </>
      )}
    </div>
  );
}
