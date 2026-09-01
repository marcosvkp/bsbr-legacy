"""Testes da paginação do ScoreSaber (regressão do `len(batch) < 100`)."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.scoresaber import ScoreSaberClient


def raw_score(base: int = 900_000, rank: int = 1) -> dict:
    return {
        "baseScore": base,
        "modifiedScore": base,
        "rank": rank,
        "fullCombo": True,
        "leaderboardPlayerInfo": {"id": f"76561198{rank:07d}", "name": f"P{rank}"},
    }


def page_payload(scores: list[dict], total: int, page: int, items_per_page: int = 12) -> dict:
    return {"scores": scores, "metadata": {"total": total, "itemsPerPage": items_per_page, "page": page}}


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self.status_code = status
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeHTTP:
    """Cliente HTTP falso: mapeia página → resposta; página ausente = falha."""

    def __init__(self, pages: dict[int, FakeResponse]):
        self.pages = pages
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url: str, params: dict | None = None):
        self.calls.append((url, dict(params or {})))
        page = (params or {}).get("page", 1)
        resp = self.pages.get(page)
        if resp is None:
            raise httpx.HTTPError(f"página {page} fora do ar")
        return resp


def make_client(pages: dict[int, FakeResponse]) -> ScoreSaberClient:
    return ScoreSaberClient(client=FakeHTTP(pages))


async def test_pagination_follows_metadata_total():
    """Página de 12 + página de 4 = 16 scores, 2 chamadas, exhausted=True."""
    p1 = page_payload([raw_score(rank=i) for i in range(1, 13)], total=16, page=1)
    p2 = page_payload([raw_score(rank=i) for i in range(13, 17)], total=16, page=2)
    fake = FakeHTTP({1: FakeResponse(p1), 2: FakeResponse(p2)})
    client = ScoreSaberClient(client=fake)

    result = await client.leaderboard_scores_by_id_with_status(123)
    assert len(result.scores) == 16
    assert result.transport_ok is True
    assert result.exhausted is True
    assert result.pages_fetched == 2
    assert [c[0] for c in fake.calls] == [
        f"{client.base_url}/leaderboard/by-id/123/scores",
        f"{client.base_url}/leaderboard/by-id/123/scores",
    ]
    assert [c[1] for c in fake.calls] == [{"page": 1}, {"page": 2}]


async def test_max_pages_is_deliberate_cap_not_exhaustion():
    """max_pages corta antes do fim: transport_ok=True mas exhausted=False."""
    p1 = page_payload([raw_score(rank=i) for i in range(1, 13)], total=100, page=1)
    client = make_client({1: FakeResponse(p1)})

    result = await client.leaderboard_scores_by_id_with_status(1, max_pages=1)
    assert len(result.scores) == 12
    assert result.transport_ok is True
    assert result.exhausted is False
    assert result.pages_fetched == 1


async def test_empty_page_ends_collection():
    p1 = page_payload([raw_score(rank=i) for i in range(1, 13)], total=100, page=1)
    p2 = page_payload([], total=100, page=2)
    client = make_client({1: FakeResponse(p1), 2: FakeResponse(p2)})

    result = await client.leaderboard_scores_by_id_with_status(1)
    assert len(result.scores) == 12
    assert result.exhausted is True
    assert result.pages_fetched == 2


async def test_transport_failure_marks_sample_invalid(monkeypatch):
    """Falha na 2ª página: resposta parcial NÃO é amostra válida (transport_ok=False)."""
    import app.integrations.scoresaber as ss

    async def _no_sleep(_s):
        return None

    monkeypatch.setattr(ss.asyncio, "sleep", _no_sleep)  # retries rápidos
    p1 = page_payload([raw_score(rank=i) for i in range(1, 13)], total=100, page=1)
    client = make_client({1: FakeResponse(p1)})  # página 2 levanta HTTPError

    result = await client.leaderboard_scores_by_id_with_status(1)
    assert len(result.scores) == 12
    assert result.transport_ok is False
    assert result.exhausted is False
    assert result.pages_fetched == 1


async def test_country_param_forwarded():
    p1 = page_payload([raw_score()], total=1, page=1)
    fake = FakeHTTP({1: FakeResponse(p1)})
    client = ScoreSaberClient(client=fake)

    out = await client.leaderboard_scores_by_id(1, country="BR")
    assert len(out) == 1
    assert fake.calls[0][1] == {"page": 1, "countries": "BR"}


async def test_wrapper_returns_plain_score_list():
    p1 = page_payload([raw_score()], total=1, page=1)
    client = make_client({1: FakeResponse(p1)})

    out = await client.leaderboard_scores_by_id(1)
    assert isinstance(out, list)
    assert len(out) == 1
