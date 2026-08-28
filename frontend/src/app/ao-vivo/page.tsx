import type { Metadata } from "next";
import { getJson } from "@/lib/api";
import type { LiveRecentResponse } from "@/lib/types";
import { BackendOffline } from "@/components/empty-state";
import { LiveFeed } from "./live-feed";

export const metadata: Metadata = {
  title: "Ao Vivo",
};

export default async function AoVivoPage() {
  let initial: LiveRecentResponse["items"] = [];
  try {
    initial = (await getJson<LiveRecentResponse>("/live/recent")).items;
  } catch {
    return <BackendOffline what="o scorefeed ao vivo" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-black tracking-tight">Ao Vivo</h1>
        <p className="text-sm text-muted">
          Scores capturados em tempo real do feed mundial do ScoreSaber.
        </p>
      </div>
      <LiveFeed initial={initial} />
    </div>
  );
}
