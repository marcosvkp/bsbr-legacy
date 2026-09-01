"""Cliente assíncrono da API do BeatLeader com rate limit compartilhado.

Endpoints usados (validados contra `references/beatleader_full_undocumented.json`
e chamadas reais em 2026-08-29):
- /player/{id}                  → perfil completo (socials, linkedIds, platform)
- /players?search=&countries=BR → busca de jogador (fallback do resolver)
- /leaderboard/{id}             → leaderboard (song.hash, difficulty)
- /leaderboards/hash/{hash}     → leaderboards de um mapa por hash (qualificação)
- /leaderboard/scores/{id}?countries= → scores paginados (sync batch)
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter

_RETRY_STATUS = {429, 500, 502, 503}
_MAX_ATTEMPTS = 3

# Serviços de rede social possíveis no campo `socials[].service`.
_SS_SERVICE_NAMES = ("scoresaber", "score saber", "steam")


def extract_ss_id_from_socials(socials: list[dict[str, Any]] | None) -> str | None:
    """Extrai o ss_id do ScoreSaber dos socials do BeatLeader.

    O campo `socials` cobre redes sociais (Discord, BeatSaver, etc.) e pode
    não listar ScoreSaber — a fonte primária do vínculo é o Steam ID (o SS id
    de jogadores Steam é o próprio Steam ID). Este é o fallback secundário:
    procura social com service/link contendo "scoresaber" e extrai o id do
    final da URL `https://scoresaber.com/u/<id>`.
    """
    for social in socials or []:
        service = str(social.get("service") or "").lower()
        link = str(social.get("link") or "")
        haystack = f"{service} {link}"
        if not any(name in haystack for name in _SS_SERVICE_NAMES):
            continue
        match = re.search(r"/(?:u|user|profile)/(\d+)", link)
        if match:
            return match.group(1)
        uid = str(social.get("userId") or "")
        if uid.isdigit():
            return uid
    return None


class BeatLeaderClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = settings.beatleader_base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "bsbr/2.0 (beatleader-resolver)"},
        )
        self._limiter = limiter or SlidingWindowLimiter(
            "beatleader", settings.scoresaber_max_calls, settings.scoresaber_period_seconds
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        url = f"{self.base_url}{path}"
        for attempt in range(_MAX_ATTEMPTS):
            await self._limiter.acquire()
            try:
                resp = await self._client.get(url, params=params)
            except httpx.HTTPError:
                resp = None
            if resp is not None and resp.status_code == 200:
                return resp.json()
            if resp is None or resp.status_code in _RETRY_STATUS:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            return None  # 404 etc: não insiste
        return None

    # ── Players ───────────────────────────────────────────────────────────

    async def player_full(self, player_id: str) -> dict[str, Any] | None:
        """GET /player/{id} — perfil completo (socials, linkedIds, platform)."""
        return await self._get(f"/player/{player_id}")

    async def search_players(
        self,
        search: str,
        country: str | None = "BR",
        count: int = 20,
    ) -> list[dict[str, Any]]:
        """GET /players?search=&countries= — lista de jogadores (fallback)."""
        params: dict[str, Any] = {"search": search, "page": 1, "count": count, "sortBy": "pp"}
        if country:
            params["countries"] = country
        data = await self._get("/players", params=params)
        if not data:
            return []
        return data.get("data") if isinstance(data, dict) else data

    # ── Leaderboards ──────────────────────────────────────────────────────

    async def ranked_leaderboards(
        self,
        *,
        sort_by: str = "stars",
        order: str = "desc",
        count: int = 40,
        page: int = 1,
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Busca de leaderboards (`/leaderboards?ranked=true`).

        Devolve ``(data, total)``. Cada item traz ``id``, ``song.hash``,
        ``song.name``, ``difficulty.stars`` e ``difficulty.maxScore``. Usada
        pelo dataset de referência (escala do BL chega ~15,8★, ancorando o
        trecho alto onde o ScoreSaber para em 14,58★).
        """
        params: dict[str, Any] = {
            "page": page,
            "count": count,
            "ranked": "true",
            "sortBy": sort_by,
            "order": order,
        }
        data = await self._get("/leaderboards", params)
        if not data:
            return [], None
        metadata = data.get("metadata") or {}
        return data.get("data", []), metadata.get("total")

    async def leaderboard_by_id(self, leaderboard_id: str) -> dict[str, Any] | None:
        """GET /leaderboard/{id} — song.hash + difficulty (value/name/status)."""
        return await self._get(f"/leaderboard/{leaderboard_id}")

    async def leaderboards_by_hash(self, hash_: str) -> list[dict[str, Any]]:
        """GET /leaderboards/hash/{hash} — leaderboards de um mapa (qualificação)."""
        data = await self._get(f"/leaderboards/hash/{hash_}")
        if not data:
            return []
        return data.get("leaderboards") if isinstance(data, dict) else data

    async def leaderboard_scores(
        self,
        leaderboard_id: str,
        country: str | None = "BR",
        page: int = 1,
        count: int = 100,
    ) -> list[dict[str, Any]]:
        """GET /leaderboard/scores/{id}?countries= — scores paginados (batch)."""
        params: dict[str, Any] = {"page": page, "count": count, "sortBy": "pp"}
        if country:
            params["countries"] = country
        data = await self._get(f"/leaderboard/scores/{leaderboard_id}", params=params)
        if not data:
            return []
        return data.get("scores") if isinstance(data, dict) else data
