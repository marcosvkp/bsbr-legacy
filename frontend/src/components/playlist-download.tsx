"use client";

import { API_BASE } from "@/lib/api";
import { formatInt } from "@/lib/format";

function DownloadIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
      <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Botões de download das playlists (.bplist) com syncURL.
 * Client component: monta o href com a URL pública da API (NEXT_PUBLIC_API_URL),
 * que funciona tanto atrás do proxy nginx quanto no dev server.
 */
export function PlaylistDownload({ total }: { total: number }) {
  return (
    <div className="flex items-center gap-2">
      <a
        href={`${API_BASE}/playlists/ranked.bplist`}
        className="inline-flex h-9 items-center gap-2 rounded-md border border-border-subtle bg-surface px-3 text-xs font-bold text-foreground transition-colors hover:bg-surface-2"
      >
        <DownloadIcon />
        Playlist ({formatInt(total)} mapas)
      </a>
      <a
        href={`${API_BASE}/playlists/latest.bplist`}
        className="inline-flex h-9 items-center gap-2 rounded-md border border-accent/40 bg-accent/10 px-3 text-xs font-bold text-white transition-colors hover:bg-accent/20"
      >
        <DownloadIcon />
        Novos
      </a>
    </div>
  );
}
