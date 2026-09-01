"use client";

import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";

interface MapActionsProps {
  beatsaverId: string | null;
  hash: string;
}

/** Link para o BeatSaver + botão de copiar o código do mapa (beatsaver_id). */
export function MapActions({ beatsaverId, hash }: MapActionsProps) {
  const [copied, setCopied] = useState(false);
  const code = beatsaverId ?? hash;

  const copyCode = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      // Fallback para ambientes sem Clipboard API (http antigo etc.)
      const ta = document.createElement("textarea");
      ta.value = code;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }, [code]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      {beatsaverId ? (
        <a
          href={`https://beatsaver.com/maps/${encodeURIComponent(beatsaverId)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm font-semibold text-foreground transition-colors hover:border-accent/50 hover:bg-surface-2 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/beatsaver-icon.png"
            alt="BeatSaver"
            className="h-4 w-4 object-contain"
            width={16}
            height={16}
          />
          Ver no BeatSaver
        </a>
      ) : null}
      <Button variant="secondary" size="md" onClick={copyCode} aria-live="polite">
        {copied ? (
          <span className="text-success">Copiado!</span>
        ) : (
          <>
            <svg
              aria-hidden="true"
              className="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            Copiar código
          </>
        )}
      </Button>
    </div>
  );
}
