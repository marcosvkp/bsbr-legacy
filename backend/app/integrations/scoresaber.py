"""Cliente assíncrono da API do ScoreSaber com rate limit compartilhado.

Endpoints usados (mesmos do legado `references/bsbr/app/ppcalc/rankedbr.py`,
portados para httpx assíncrono):
- /players?page=&countries=BR          → jogadores por país (paginado)
- /player/{id}/full                    → perfil completo
- /player/{id}/scores?page=&sort=top   → scores do jogador
- /leaderboard/by-id/{id}/scores?page= → scores de um leaderboard
- /leaderboard/by-hash/{hash}/info     → info de leaderboard (stars, maxScore)
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter

_RETRY_STATUS = {429, 500, 502, 503}
_MAX_ATTEMPTS = 3


class ScoreSaberClient:
    def __init__(self, client: httpx.AsyncClient | None = None, limiter: SlidingWindowLimiter | None = None) -> None:
        settings = get_settings()
        self.base_url = settings.scoresaber_base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._limiter = limiter or SlidingWindowLimiter(
            "scoresaber", settings.scoresaber_max_calls, settings.scoresaber_period_seconds
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

    # ── Players ────────────────────────────────────────────────────────────

    async def players_by_country(self, country: str = "BR", max_pages: int | None = None) -> list[dict[str, Any]]:
        """Pagina /players até a página virar incompleta (padrão do legado)."""
        players: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._get("/players", {"page": page, "countries": country})
            if not data:
                break
            batch = data.get("players", [])
            players.extend(batch)
            if len(batch) < data.get("meta", {}).get("itemsPerPage", batch and len(batch) or 0) or (
                max_pages is not None and page >= max_pages
            ):
                break
            page += 1
        return players

    async def player_full(self, player_id: str) -> dict[str, Any] | None:
        return await self._get(f"/player/{player_id}/full")

    async def player_scores(
        self,
        player_id: str,
        *,
        sort: str = "top",
        limit: int = 100,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        scores: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._get(
                f"/player/{player_id}/scores",
                {"limit": limit, "page": page, "sort": sort, "withMetadata": "true"},
            )
            if not data:
                break
            batch = data.get("playerScores", [])
            if not batch:
                break
            scores.extend(batch)
            if max_pages is not None and page >= max_pages:
                break
            page += 1
        return scores

    # ── Leaderboards ───────────────────────────────────────────────────────

    async def leaderboard_scores_by_id(
        self,
        leaderboard_id: int | str,
        *,
        country: str | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        scores: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] = {"page": page}
            if country:
                params["countries"] = country
            data = await self._get(f"/leaderboard/by-id/{leaderboard_id}/scores", params)
            if not data:
                break
            batch = data.get("scores", [])
            if not batch:
                break
            scores.extend(batch)
            if len(batch) < 100 or (max_pages is not None and page >= max_pages):
                break
            page += 1
        return scores

    async def leaderboard_info_by_hash(self, map_hash: str, difficulty_rank: int) -> dict[str, Any] | None:
        return await self._get(
            f"/leaderboard/by-hash/{map_hash}/info",
            {"difficulty": difficulty_rank},
        )

    async def leaderboard_info_by_id(self, leaderboard_id: int | str) -> dict[str, Any] | None:
        """GET /leaderboard/by-id/{id}/info — maxScore, stars, difficulty."""
        return await self._get(f"/leaderboard/by-id/{leaderboard_id}/info")

    async def leaderboard_scores_by_hash(
        self,
        map_hash: str,
        difficulty_rank: int,
        *,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        scores: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            data = await self._get(
                f"/leaderboard/by-hash/{map_hash}/scores",
                {"difficulty": difficulty_rank, "page": page},
            )
            if not data:
                break
            batch = data.get("scores", [])
            if not batch:
                break
            scores.extend(batch)
        return scores

    async def leaderboard_difficulties(self, map_hash: str) -> list[dict[str, Any]]:
        data = await self._get(f"/leaderboard/get-difficulties/{map_hash}")
        return data if isinstance(data, list) else []
