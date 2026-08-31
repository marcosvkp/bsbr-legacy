"""Testes das sugestões de mapas (jogador) e da revisão no admin."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import Base
from app.core.user_session import cookie_value
from app.main import app
from app.models import Difficulty, Map, MapStatus, MapSuggestion, MapSuggestionStatus, Player

STEAM_ID = "76561198000000001"

FAKE_METADATA = {
    "hash": "h1",
    "beatsaver_id": "b1",
    "name": "Mapa Teste",
    "mapper": "Mapper",
    "song_author": "Autor",
    "bpm": 130.0,
    "cover_url": "http://cover/1.jpg",
}


@pytest.fixture(autouse=True)
def _settings():
    get_settings().admin_token = "test-token"
    yield
    get_settings().admin_token = None


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/sug.db")
    import app.core.db as dbmod

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/sug.db")
    dbmod.engine = engine
    dbmod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clean_limiters():
    """Isola o registry de rate-limit por IP entre testes."""
    import app.services.suggestions as svc

    svc._ip_limiters.clear()
    yield
    svc._ip_limiters.clear()


@pytest.fixture
def logged(client):
    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    return client


def _admin_headers() -> dict:
    return {"X-Admin-Token": "test-token"}


async def _fake_metadata(source: str) -> dict:
    return {**FAKE_METADATA, "hash": f"h{source}", "beatsaver_id": source, "name": f"Mapa {source}"}


async def _fake_const_metadata(_source: str) -> dict:
    return dict(FAKE_METADATA)


async def _fake_empty(_source: str) -> dict:
    return {}


async def test_requires_login(client):
    r = client.post("/api/v1/suggestions", json={"source": "abc"})
    assert r.status_code == 401


async def test_my_requires_login(client):
    r = client.get("/api/v1/suggestions/me")
    assert r.status_code == 401


async def test_create_suggestion(logged, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_const_metadata)
    r = logged.post(
        "/api/v1/suggestions",
        json={"source": "https://beatsaver.com/maps/b1", "note": "mapa brabo"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["hash"] == "h1"
    assert body["status"] == "pending"
    assert body["note"] == "mapa brabo"
    assert body["name"] == "Mapa Teste"

    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        row = (await s.scalars(select(MapSuggestion))).first()
        assert row is not None
        assert row.ss_id == STEAM_ID
        assert row.status == MapSuggestionStatus.PENDING


async def test_invalid_source(logged):
    r = logged.post("/api/v1/suggestions", json={"source": "not a source!!!"})
    assert r.status_code == 422


async def test_map_not_found_on_beatsaver(logged, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_empty)
    r = logged.post("/api/v1/suggestions", json={"source": "b1"})
    assert r.status_code == 422
    assert "BeatSaver" in r.json()["detail"]


async def test_limit_3_pending(logged, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_metadata)
    for i in range(3):
        r = logged.post("/api/v1/suggestions", json={"source": f"id{i}"})
        assert r.status_code == 201, r.text
    r = logged.post("/api/v1/suggestions", json={"source": "id3"})
    assert r.status_code == 422
    assert "3 sugest" in r.json()["detail"]


async def test_duplicate_pending(logged, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_const_metadata)
    logged.post("/api/v1/suggestions", json={"source": "b1"})
    r = logged.post("/api/v1/suggestions", json={"source": "b1"})
    assert r.status_code == 409


async def test_reject_ranked_map(logged, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_const_metadata)
    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        s.add(Map(hash="h1", name="Ranked", status=MapStatus.RANKED))
        await s.commit()
    r = logged.post("/api/v1/suggestions", json={"source": "b1"})
    assert r.status_code == 422
    assert "rankeado" in r.json()["detail"]


async def test_rate_limit_by_ip_unit():
    import app.services.suggestions as svc

    for _ in range(svc.SUGGEST_IP_MAX):
        assert await svc.ip_can_suggest("203.0.113.7")
    assert not await svc.ip_can_suggest("203.0.113.7")


async def test_rate_limit_429(logged, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_const_metadata)
    async def _no_suggest(_ip: str) -> bool:
        return False
    monkeypatch.setattr(ep, "ip_can_suggest", _no_suggest)
    r = logged.post("/api/v1/suggestions", json={"source": "b1"})
    assert r.status_code == 429


async def test_my_suggestions_paginated(logged, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_metadata)
    logged.post("/api/v1/suggestions", json={"source": "a1"})
    logged.post("/api/v1/suggestions", json={"source": "a2"})
    r = logged.get("/api/v1/suggestions/me")
    assert r.status_code == 200
    body = r.json()
    assert body["active_count"] == 2
    assert body["max_active"] == 3
    assert body["total"] == 2
    assert len(body["items"]) == 2


async def test_admin_list_suggestions(client, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_metadata)
    client.post("/api/v1/suggestions", json={"source": "a1"})

    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        s.add(Player(ss_id=STEAM_ID, name="Marco", country="BR"))
        await s.commit()

    r = client.get("/api/v1/admin/suggestions", headers=_admin_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["player_name"] == "Marco"
    assert item["status"] == "pending"


async def test_admin_list_requires_auth(client):
    r = client.get("/api/v1/admin/suggestions")
    assert r.status_code == 403


async def test_admin_approve_creates_candidate(client, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_metadata)
    client.post("/api/v1/suggestions", json={"source": "a1"})

    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        sid = (await s.scalars(select(MapSuggestion))).first().id

    r = client.post(f"/api/v1/admin/suggestions/{sid}/approve", headers=_admin_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["map_id"] is not None

    async with SessionLocal() as s:
        m = (await s.scalars(select(Map))).first()
        assert m is not None
        assert m.status == MapStatus.CANDIDATE
        assert m.submitted_by == STEAM_ID
        # ML não roda na aprovação: o candidato nasce sem difficulties
        diff_count = await s.scalar(
            select(func.count()).select_from(Difficulty).where(Difficulty.map_id == m.id)
        )
        assert diff_count == 0
        sug = await s.get(MapSuggestion, sid)
        assert sug.status == MapSuggestionStatus.APPROVED
        assert sug.reviewed_at is not None


async def test_admin_approve_duplicate(client, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_const_metadata)
    client.post("/api/v1/suggestions", json={"source": "b1"})

    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        sid = (await s.scalars(select(MapSuggestion))).first().id

    client.post(f"/api/v1/admin/suggestions/{sid}/approve", headers=_admin_headers())
    # segundo approve (sugestão já revisada)
    r = client.post(f"/api/v1/admin/suggestions/{sid}/approve", headers=_admin_headers())
    assert r.status_code == 422


async def test_admin_approve_conflict_with_existing_map(client, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_const_metadata)
    client.post("/api/v1/suggestions", json={"source": "b1"})

    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        sid = (await s.scalars(select(MapSuggestion))).first().id
        s.add(Map(hash="h1", name="Existente", status=MapStatus.CANDIDATE))
        await s.commit()

    r = client.post(f"/api/v1/admin/suggestions/{sid}/approve", headers=_admin_headers())
    assert r.status_code == 409


async def test_admin_reject(client, monkeypatch):
    import app.api.v1.endpoints.suggestions as ep

    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    monkeypatch.setattr(ep, "fetch_metadata_light", _fake_metadata)
    client.post("/api/v1/suggestions", json={"source": "a1"})

    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        sid = (await s.scalars(select(MapSuggestion))).first().id

    r = client.post(f"/api/v1/admin/suggestions/{sid}/reject", headers=_admin_headers())
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    # slot liberado: o jogador pode sugerir de novo
    async with SessionLocal() as s:
        sug = await s.get(MapSuggestion, sid)
        assert sug.status == MapSuggestionStatus.REJECTED
