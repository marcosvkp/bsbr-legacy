"use client";

import { useState } from "react";

export interface PlayerAvatarProps {
  name: string;
  avatarUrl: string | null;
  /** Tamanho em px. */
  size?: number;
}

/** Avatar do jogador com fallback para iniciais quando a imagem falha ou falta. */
export function PlayerAvatar({ name, avatarUrl, size = 36 }: PlayerAvatarProps) {
  const [failed, setFailed] = useState(false);
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");

  if (!avatarUrl || failed) {
    return (
      <span
        aria-hidden="true"
        style={{ width: size, height: size, fontSize: Math.max(size * 0.38, 10) }}
        className="flex shrink-0 items-center justify-center rounded-full bg-surface-2 font-bold text-muted"
      >
        {initials || "?"}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- avatares/covers vêm de CDNs externos (ScoreSaber/BeatSaver)
    <img
      src={avatarUrl}
      alt={`Avatar de ${name}`}
      width={size}
      height={size}
      loading="lazy"
      onError={() => setFailed(true)}
      style={{ width: size, height: size }}
      className="shrink-0 rounded-full bg-surface-2 object-cover"
    />
  );
}
