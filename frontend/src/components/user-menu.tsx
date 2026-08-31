"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { API_BASE, getJson, postJson } from "@/lib/api";
import type { MeResponse } from "@/lib/types";
import { PlayerAvatar } from "@/components/player-avatar";
import { Button } from "@/components/ui/button";

/** Botão de sessão do site: "Entrar com Steam" ou avatar+nome com menu. */
export function UserMenu() {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [checked, setChecked] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getJson<MeResponse>("/auth/me")
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(() => {
    window.location.assign(`${API_BASE}/auth/steam/login`);
  }, []);

  const logout = useCallback(async () => {
    try {
      await postJson("/auth/logout", {});
    } catch {
      // Sem rede o cookie é apagado mesmo assim pelo Set-Cookie do backend.
    }
    setUser(null);
    setOpen(false);
    window.location.assign("/");
  }, []);

  if (!checked) {
    return <div className="h-8 w-20 animate-pulse rounded-md bg-surface-2" aria-hidden="true" />;
  }

  if (!user) {
    return (
      <Button variant="secondary" size="sm" onClick={login}>
        Entrar com Steam
      </Button>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`Menu de ${user.name}`}
        className="flex items-center gap-2 rounded-md px-1.5 py-1 transition-colors hover:bg-surface"
      >
        <PlayerAvatar name={user.name} avatarUrl={user.avatar_url} size={26} />
        <span className="hidden max-w-32 truncate text-sm font-medium text-foreground md:inline">
          {user.name}
        </span>
      </button>
      {open && (
        <>
          <button
            type="button"
            aria-label="Fechar menu"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 z-20 mt-1 w-44 overflow-hidden rounded-md border border-border-subtle bg-surface shadow-lg">
            <Link
              href={`/jogadores/${user.ss_id}`}
              onClick={() => setOpen(false)}
              className="block px-3 py-2 text-sm text-foreground hover:bg-surface-2"
            >
              Meu perfil
            </Link>
            <button
              type="button"
              onClick={logout}
              className="block w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-surface-2"
            >
              Sair
            </button>
          </div>
        </>
      )}
    </div>
  );
}
