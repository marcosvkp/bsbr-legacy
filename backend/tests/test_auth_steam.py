"""Testes do OAuth Steam (OpenID 2.0) — login/callback/me/logout.

Mocka o httpx (check_authentication e GetPlayerSummaries) para não depender
da rede nem de credenciais reais.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import Base
from app.core.user_session import cookie_value
from app.main import app
from app.models import Player

OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
STEAM_ID = "76561198000000000"
CALLBACK = "http://localhost:18000/api/v1/auth/steam/callback"


class FakeResponse:
    def __init__(self, text: str = "", json_data: dict | None = None, status_code: int = 200) -> None:
        self._text = text
        self._json = json_data or {}
        self.status_code = status_code

    def json(self) -> dict:
        return self._json

    @property
    def text(self) -> str:
        return self._text


class FakeAsyncClient:
    def __init__(self, *, timeout: float | None = None, openid_valid: bool = True, profile: list | None = None) -> None:
        self.openid_valid = openid_valid
        self.profile = profile or []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, data: dict | None = None, **kwargs: object):
        if url == OPENID_ENDPOINT:
            return FakeResponse(text="is_valid:true\n" if self.openid_valid else "is_valid:false\n")
        return FakeResponse(status_code=404)

    async def get(self, url: str, params: dict | None = None, **kwargs: object):
        if "GetPlayerSummaries" in url:
            return FakeResponse(json_data={"response": {"players": self.profile}})
        return FakeResponse(status_code=404)


@pytest.fixture(autouse=True)
def _settings():
    get_settings().admin_token = "test-token"
    get_settings().steam_return_to = CALLBACK
    get_settings().frontend_base_url = "http://localhost:3000"
    get_settings().steam_api_key = "test-key"
    yield
    get_settings().admin_token = None
    get_settings().steam_return_to = None
    get_settings().frontend_base_url = "http://localhost:3000"
    get_settings().steam_api_key = None


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/auth.db")
    import app.core.db as dbmod

    engine = create_engine_for_test(tmp_path)
    dbmod.engine = engine
    dbmod.SessionLocal = sessionmaker_for_test(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    await engine.dispose()


def create_engine_for_test(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/auth.db")


def sessionmaker_for_test(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(engine, expire_on_commit=False)


def _login_and_state(client) -> str:
    """Passa pelo /auth/steam/login e devolve o state do Set-Cookie."""
    r = client.get("/api/v1/auth/steam/login", follow_redirects=False)
    assert r.status_code == 307
    m = re.search(r"bsbr_steam_state=([0-9a-f]+)", r.headers.get("set-cookie", ""))
    assert m
    return m.group(1)


def _callback_params(state: str, *, claimed_id: str | None = None, return_to: str | None = None) -> dict:
    return {
        "state": state,
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "id_res",
        "openid.identity": f"https://steamcommunity.com/openid/id/{STEAM_ID}",
        "openid.claimed_id": claimed_id or f"https://steamcommunity.com/openid/id/{STEAM_ID}",
        "openid.return_to": return_to or f"{CALLBACK}?state={state}",
        "openid.sig": "abc",
        "openid.signed": "claimed_id,identity,return_to",
        "openid.assoc_handle": "h",
        "openid.op_endpoint": OPENID_ENDPOINT,
    }


async def test_steam_login_redirects_to_openid(client):
    r = client.get("/api/v1/auth/steam/login", follow_redirects=False)
    assert r.status_code == 307
    location = r.headers["location"]
    assert location.startswith(OPENID_ENDPOINT + "?")
    assert "openid.mode=checkid_setup" in location
    assert "openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select" in location
    assert "openid.realm=http%3A%2F%2Flocalhost%3A18000" in location
    assert "bsbr_steam_state=" in r.headers["set-cookie"]


async def test_steam_login_requires_return_to(client):
    get_settings().steam_return_to = None
    r = client.get("/api/v1/auth/steam/login", follow_redirects=False)
    assert r.status_code == 500


async def test_steam_callback_valid_creates_player(client, monkeypatch):
    import app.api.v1.endpoints.auth as authmod

    monkeypatch.setattr(
        authmod.httpx,
        "AsyncClient",
        lambda **kw: FakeAsyncClient(
            openid_valid=True,
            profile=[{"personaname": "Marco", "avatarfull": "http://a/1.jpg", "loccountrycode": "BR"}],
        ),
    )
    state = _login_and_state(client)
    r = client.get("/api/v1/auth/steam/callback", params=_callback_params(state), follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "http://localhost:3000"
    assert "bsbr_user_session=" in r.headers["set-cookie"]

    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        p = (await s.scalars(select(Player).where(Player.ss_id == STEAM_ID))).first()
        assert p is not None
        assert p.bl_id == STEAM_ID
        assert p.name == "Marco"
        assert p.country == "BR"


async def test_steam_callback_valid_without_profile(client, monkeypatch):
    """Sem Steam API key o login ainda funciona (nome default)."""
    import app.api.v1.endpoints.auth as authmod

    get_settings().steam_api_key = None
    monkeypatch.setattr(authmod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(openid_valid=True))
    state = _login_and_state(client)
    r = client.get("/api/v1/auth/steam/callback", params=_callback_params(state), follow_redirects=False)
    assert r.status_code == 307
    assert "bsbr_user_session=" in r.headers["set-cookie"]


async def test_steam_callback_invalid_state(client, monkeypatch):
    import app.api.v1.endpoints.auth as authmod

    monkeypatch.setattr(authmod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(openid_valid=True))
    _login_and_state(client)
    r = client.get("/api/v1/auth/steam/callback", params=_callback_params("wrong-state"), follow_redirects=False)
    assert r.status_code == 307
    assert "auth_error=state" in r.headers["location"]
    assert "bsbr_user_session" not in r.headers.get("set-cookie", "")


async def test_steam_callback_bad_claimed_id(client, monkeypatch):
    import app.api.v1.endpoints.auth as authmod

    monkeypatch.setattr(authmod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(openid_valid=True))
    state = _login_and_state(client)
    r = client.get(
        "/api/v1/auth/steam/callback",
        params=_callback_params(state, claimed_id="https://evil.example.com/id/123"),
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "auth_error=claimed_id" in r.headers["location"]


async def test_steam_callback_wrong_return_to(client, monkeypatch):
    import app.api.v1.endpoints.auth as authmod

    monkeypatch.setattr(authmod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(openid_valid=True))
    state = _login_and_state(client)
    r = client.get(
        "/api/v1/auth/steam/callback",
        params=_callback_params(state, return_to="https://evil.example.com/callback?state=x"),
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "auth_error=return_to" in r.headers["location"]


async def test_steam_callback_openid_invalid(client, monkeypatch):
    import app.api.v1.endpoints.auth as authmod

    monkeypatch.setattr(authmod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(openid_valid=False))
    state = _login_and_state(client)
    r = client.get("/api/v1/auth/steam/callback", params=_callback_params(state), follow_redirects=False)
    assert r.status_code == 307
    assert "auth_error=valida" in r.headers["location"]


async def test_me_requires_session(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_me_returns_logged_player(client):
    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        s.add(Player(ss_id=STEAM_ID, name="Marco", country="BR", rank=3))
        await s.commit()
    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["ss_id"] == STEAM_ID
    assert body["name"] == "Marco"
    assert body["rank"] == 3


async def test_logout_clears_session(client):
    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    sc = r.headers.get("set-cookie", "")
    assert "bsbr_user_session=" in sc
    assert "Max-Age=0" in sc or "expires=" in sc.lower()
