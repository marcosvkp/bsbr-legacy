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
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter

_RETRY_STATUS = {429, 500, 502, 503}
_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class LeaderboardScoresResult:
    """Resultado paginado de um leaderboard com diagnóstico de transporte.

    - ``transport_ok``: False se qualquer página falhar após as tentativas do
      cliente — resposta parcial por falha NÃO é amostra válida.
    - ``exhausted``: True quando o total informado foi alcançado ou uma página
      vazia encerrou a coleção. Se o teto deliberado (max_pages) cortar antes
      do fim, fica False (a janela superior pode ter sido usada de propósito).
    """

    scores: list[dict[str, Any]]
    transport_ok: bool
    exhausted: bool
    pages_fetched: int


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

    async def leaderboard_scores_by_id_with_status(
        self,
        leaderboard_id: int | str,
        *,
        country: str | None = None,
        max_pages: int | None = None,
    ) -> LeaderboardScoresResult:
        """Pagina os scores de um leaderboard usando os metadados da API.

        A API real devolve ``itemsPerPage=12`` mesmo sem ``limit``; o legado
        parava na 1ª página com ``len(batch) < 100`` e subcoletava o BR. Aqui
        a paginação segue ``metadata.total`` / ``itemsPerPage`` / página vazia,
        respeitando ``max_pages`` como teto deliberado.
        """
        scores: list[dict[str, Any]] = []
        page = 1
        total_hint: int | None = None
        transport_ok = True
        exhausted = False
        pages_ok = 0
        while True:
            params: dict[str, Any] = {"page": page}
            if country:
                params["countries"] = country
            data = await self._get(f"/leaderboard/by-id/{leaderboard_id}/scores", params)
            if data is None:
                transport_ok = False
                break
            pages_ok += 1
            metadata = data.get("metadata") or {}
            if page == 1:
                total_hint = metadata.get("total")
            batch = data.get("scores", [])
            scores.extend(batch)
            if not batch:
                exhausted = True
                break
            if total_hint is not None:
                if len(scores) >= total_hint:
                    exhausted = True
                    break
            elif len(batch) < metadata.get("itemsPerPage", 0):
                exhausted = True
                break
            if max_pages is not None and page >= max_pages:
                break
            page += 1
        return LeaderboardScoresResult(
            scores=scores,
            transport_ok=transport_ok,
            exhausted=exhausted,
            pages_fetched=pages_ok,
        )

    async def leaderboard_scores_by_id(
        self,
        leaderboard_id: int | str,
        *,
        country: str | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        result = await self.leaderboard_scores_by_id_with_status(
            leaderboard_id, country=country, max_pages=max_pages
        )
        return result.scores

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
