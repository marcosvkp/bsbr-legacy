"""Testes dos webhooks do Discord (admin CRUD + relatório de reweight)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import Base
from app.main import app
from app.models import WebhookConfig

ADMIN = {"X-Admin-Token": "test-token"}


@pytest.fixture(autouse=True)
def _settings():
    get_settings().admin_token = "test-token"
    get_settings().discord_webhook_url = None
    yield
    get_settings().admin_token = None
    get_settings().discord_webhook_url = None


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/wh.db")
    import app.core.db as dbmod

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/wh.db")
    dbmod.engine = engine
    dbmod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    await engine.dispose()


# ── Admin CRUD ───────────────────────────────────────────────────────────


async def test_webhooks_require_admin(client):
    r = client.get("/api/v1/admin/webhooks")
    assert r.status_code == 401


async def test_webhook_crud(client):
    # create
    r = client.post(
        "/api/v1/admin/webhooks",
        json={"url": "https://discord.com/api/webhooks/abc/def", "label": "Geral"},
        headers=ADMIN,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["enabled"] is True
    wid = body["id"]

    # duplicate → 409
    r = client.post(
        "/api/v1/admin/webhooks",
        json={"url": "https://discord.com/api/webhooks/abc/def"},
        headers=ADMIN,
    )
    assert r.status_code == 409

    # invalid url → 422
    r = client.post("/api/v1/admin/webhooks", json={"url": "not-a-url"}, headers=ADMIN)
    assert r.status_code == 422

    # list
    r = client.get("/api/v1/admin/webhooks", headers=ADMIN)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1

    # toggle off
    r = client.patch(f"/api/v1/admin/webhooks/{wid}", json={"enabled": False}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    # delete
    r = client.delete(f"/api/v1/admin/webhooks/{wid}", headers=ADMIN)
    assert r.status_code == 204
    r = client.get("/api/v1/admin/webhooks", headers=ADMIN)
    assert len(r.json()["items"]) == 0


# ─── get_webhook_urls ──────────────────────────────────────────────────────


async def test_get_webhook_urls_from_db(client):
    from app.core.db import SessionLocal
    from app.integrations.discord import get_webhook_urls

    async with SessionLocal() as s:
        s.add_all(
            [
                WebhookConfig(url="https://a.example/h", enabled=True),
                WebhookConfig(url="https://b.example/h", enabled=False),
            ]
        )
        await s.commit()
        urls = await get_webhook_urls(s)
        assert urls == ["https://a.example/h"]  # só habilitado


async def test_get_webhook_urls_env_fallback(client):
    from app.core.db import SessionLocal
    from app.integrations.discord import get_webhook_urls

    get_settings().discord_webhook_url = "https://x.example/1, https://y.example/2"
    async with SessionLocal() as s:
        urls = await get_webhook_urls(s)
        assert urls == ["https://x.example/1", "https://y.example/2"]


async def test_get_webhook_urls_empty(client):
    from app.core.db import SessionLocal
    from app.integrations.discord import get_webhook_urls

    async with SessionLocal() as s:
        assert await get_webhook_urls(s) == []


# ─── send_reweight_report ──────────────────────────────────────────────────


class FakeClient:
    def __init__(self, *, timeout=None):
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, json: dict):
        self.posts.append((url, json))
        return FakeResponse(204)


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


async def test_send_reweight_report_posts_to_all(client, monkeypatch):
    from app.core.db import SessionLocal
    from app.integrations.discord import send_reweight_report

    async with SessionLocal() as s:
        s.add_all(
            [
                WebhookConfig(url="https://a.example/h", label="A"),
                WebhookConfig(url="https://b.example/h", label="B"),
            ]
        )
        await s.commit()

    import app.integrations.discord as discordmod

    fake = FakeClient()
    monkeypatch.setattr(discordmod.httpx, "AsyncClient", lambda **kw: fake)

    rows = [
        {
            "map_name": "Bangin' Burst",
            "difficulty": "Expert+",
            "mapper": "ComplexFrequency",
            "before": 13.61,
            "after": 13.68,
        },
        {
            "map_name": "Miku",
            "difficulty": "Expert+",
            "mapper": "Tranch",
            "before": 8.86,
            "after": 7.64,
        },
    ]
    async with SessionLocal() as s:
        sent = await send_reweight_report(s, rows, title="Reweight de mapas — 31/08/2026")

    assert sent == 2  # dois webhooks
    assert len(fake.posts) == 2
    url, payload = fake.posts[0]
    assert url == "https://a.example/h"
    embed = payload["embeds"][0]
    assert embed["title"] == "Reweight de mapas — 31/08/2026"
    assert "Bangin' Burst" in embed["description"]
    assert "13.61" in embed["description"]
    assert "13.68" in embed["description"]
    assert "Miku" in embed["description"]


async def test_send_reweight_report_empty_rows(client, monkeypatch):
    from app.core.db import SessionLocal
    from app.integrations.discord import send_reweight_report

    import app.integrations.discord as discordmod

    fake = FakeClient()
    monkeypatch.setattr(discordmod.httpx, "AsyncClient", lambda **kw: fake)
    async with SessionLocal() as s:
        assert await send_reweight_report(s, []) == 0
    assert fake.posts == []


async def test_send_reweight_report_no_webhooks(client, monkeypatch):
    from app.core.db import SessionLocal
    from app.integrations.discord import send_reweight_report

    import app.integrations.discord as discordmod

    fake = FakeClient()
    monkeypatch.setattr(discordmod.httpx, "AsyncClient", lambda **kw: fake)
    async with SessionLocal() as s:
        sent = await send_reweight_report(s, [{"map_name": "X", "before": 1, "after": 2}])
    assert sent == 0
    assert fake.posts == []


# ─── apply manual NÃO dispara webhook (report sai no batch) ────────────────


async def test_admin_apply_does_not_send_webhook(client, monkeypatch):
    """O apply manual só persiste; a notificação sai quando o batch roda."""
    from app.core.db import SessionLocal
    from app.models import Difficulty, Map, MapStatus, ReweightSuggestion, SuggestionStatus

    async with SessionLocal() as s:
        m = Map(hash="c" * 40, name="Mapa Teste", mapper="MapperX", status=MapStatus.RANKED)
        s.add(m)
        await s.flush()
        d = Difficulty(
            map_id=m.id,
            characteristic="Standard",
            name="ExpertPlus",
            total_stars=8.0,
            is_ranked=True,
        )
        s.add(d)
        await s.flush()
        sug = ReweightSuggestion(
            difficulty_id=d.id,
            observed_acc=0.95,
            expected_acc=0.88,
            sample_size=11,
            delta_stars=-1.5,
            confidence="low",
            suggested_stars=6.5,
            status=SuggestionStatus.PENDING,
        )
        s.add(sug)
        s.add(WebhookConfig(url="https://a.example/h", enabled=True))
        await s.commit()
        sug_id = sug.id

    import app.integrations.discord as discordmod

    fake = FakeClient()
    monkeypatch.setattr(discordmod.httpx, "AsyncClient", lambda **kw: fake)

    r = client.post(f"/api/v1/admin/reweight/{sug_id}/apply", headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied"

    assert fake.posts == [], "apply manual não deve postar no webhook"
