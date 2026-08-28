"use client";

import { useState } from "react";
import type { ReactNode } from "react";

export interface SmartImgProps {
  src: string | null | undefined;
  alt: string;
  className?: string;
  /** Renderizado quando não há src ou a imagem falha ao carregar. */
  fallback: ReactNode;
}

/** `<img>` tolerante a CDNs externos indisponíveis: cai no fallback via onError. */
export function SmartImg({ src, alt, className, fallback }: SmartImgProps) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) return <>{fallback}</>;

  return (
    // eslint-disable-next-line @next/next/no-img-element -- covers/avatars vêm de CDNs externos (BeatSaver/ScoreSaber)
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className={className}
    />
  );
}
