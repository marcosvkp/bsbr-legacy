"""Resolver de contas BeatLeader → ScoreSaber.

Um jogador tem contas nos dois rankings; o Score armazenado é 1 por
(player, difficulty), então o BSBR precisa saber que o playerId do
BeatLeader é o MESMO humano do ss_id.

Regras (validadas com a API real em 2026-08-29):
1. Para jogadores Steam (a maioria no BR), o id do BeatLeader É o Steam ID
   e o ScoreSaber id também é o Steam ID → bl_id == ss_id, vínculo direto.
2. Fallback: `GET /player/{bl_id}` e extrair o ScoreSaber dos `socials`.
3. Último recurso: busca `/players?search=` (nome+país) e casa com um Player
   local existente; se ainda não achar, cria um Player com bl_id (o batch
   tenta resolver de novo depois).

Cache em memória (TTL 1h) para não bater na API a cada score ao vivo.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.beatleader import BeatLeaderClient, extract_ss_id_from_socials
from app.models import Player

logger = logging.getLogger(__name__)

# Cache: bl_id -> ss_id (ou "" para "sem vínculo"). TTL 1h.
_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 3600


def _cache_get(bl_id: str) -> str | None:
    entry = _CACHE.get(bl_id)
    if entry is None:
        return None
    ss_id, ts = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(bl_id, None)
        return None
    return ss_id or None


def _cache_set(bl_id: str, ss_id: str | None) -> None:
    _CACHE[bl_id] = (ss_id or "", time.monotonic())


def clear_cache() -> None:
    _CACHE.clear()


def _bl_player_is_steam_ss(bl_id: str) -> bool:
    """O id do BL é o Steam ID? (17 dígitos, padrão Steam) — então é o ss_id."""
    return len(bl_id) == 17 and bl_id.isdigit()


def _resolve_by_platform(player: dict[str, Any]) -> str | None:
    """Vínculo primário: id do BL == Steam ID == ss_id.

    `linkedIds.steamId` também confirma (quando presente).
    """
    linked = player.get("linkedIds") or {}
    steam_id = linked.get("steamId")
    if steam_id:
        return str(steam_id)
    player_id = str(player.get("id") or "")
    if _bl_player_is_steam_ss(player_id) and player.get("platform") == "steam":
        return player_id
    return None


async def resolve_bl_player(
    session: AsyncSession,
    bl_id: str,
    client: BeatLeaderClient | None = None,
    *,
    player_name: str | None = None,
    player_country: str | None = None,
) -> Player:
    """Garante um Player local para o jogador do BeatLeader.

    - Se já existe Player com bl_id → retorna.
    - Resolve ss_id (steam id direto, socials, ou busca por nome/país) e faz
      upsert do Player por ss_id, gravando bl_id.
    - Se não resolveu nada, cria Player(ss_id=bl_id, bl_id=bl_id) — o batch
      tenta resolver de novo depois (bl_resolved_at nulo).
    """
    existing = (
        await session.scalars(select(Player).where(Player.bl_id == bl_id).limit(1))
    ).first()
    if existing is not None:
        return existing

    # Vínculo primário sem API: id do BL é Steam ID → é o próprio ss_id.
    resolved_direct = False
    if _bl_player_is_steam_ss(bl_id):
        ss_id = bl_id
        resolved_direct = True
        _cache_set(bl_id, ss_id)
    else:
        ss_id = _cache_get(bl_id)

    # 1) chave da API para vínculo por plataforma/socials (só se ainda não
    #    resolvido pelo Steam ID direto)
    if ss_id is None and client is not None:
        player = await client.player_full(bl_id)
        if player:
            ss_id = _resolve_by_platform(player) or extract_ss_id_from_socials(
                player.get("socials")
            )
            if ss_id:
                _cache_set(bl_id, ss_id)
            else:
                _cache_set(bl_id, None)  # não insiste por 1h

    # 2) fallback: busca por nome + país e casa com Player local
    if ss_id is None and client is not None and player_name:
        try:
            candidates = await client.search_players(player_name, country=player_country)
        except Exception:  # noqa: BLE001 — busca é best-effort
            logger.exception("erro na busca BeatLeader por %r", player_name)
            candidates = []
        matches = []
        for cand in candidates:
            cand_name = str(cand.get("name") or "")
            if cand_name.lower() == player_name.lower():
                matches.append(cand)
        if len(matches) == 1:
            cand_id = str(matches[0].get("id") or "")
            linked = matches[0].get("linkedIds") or {}
            steam = linked.get("steamId")
            if steam and _bl_player_is_steam_ss(str(steam)):
                ss_id = str(steam)
            elif cand_id:
                ss_id = cand_id
            if ss_id:
                _cache_set(bl_id, ss_id)
        elif len(matches) > 1:
            logger.warning(
                "resolve %r ambíguo no BeatLeader (%d matches) — sem vínculo automático",
                player_name,
                len(matches),
            )

    # upsert por ss_id (ou cria com o próprio bl_id como ss_id provisório)
    target_ss = ss_id or bl_id
    player = (
        await session.scalars(select(Player).where(Player.ss_id == target_ss).limit(1))
    ).first()
    if player is None:
        player = Player(
            ss_id=target_ss,
            name=player_name or target_ss,
            country=(player_country or "").upper()[:8] or None,
        )
        session.add(player)
    if player.bl_id is None or player.bl_id != bl_id:
        player.bl_id = bl_id
    if ss_id:
        player.bl_resolved_at = datetime.now(timezone.utc)
        if not player.name and player_name:
            player.name = player_name
    await session.flush()
    return player
