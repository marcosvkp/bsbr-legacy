"""Testes de autenticação do admin por sessão Steam + tabela staff."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import Base
from app.core.user_session import cookie_value
from app.main import app
from app.models import StaffUser

STEAM_ID = "76561198000000001"


@pytest.fixture(autouse=True)
def _settings():
    get_settings().admin_token = "test-token"
    yield
    get_settings().admin_token = None


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/staff.db")
    import app.core.db as dbmod

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/staff.db")
    dbmod.engine = engine
    dbmod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    await engine.dispose()


async def _add_staff(ss_id: str = STEAM_ID, role: str = "owner") -> int:
    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        m = StaffUser(ss_id=ss_id, role=role, name="Staff")
        s.add(m)
        await s.commit()
        return m.id


async def test_anonymous_gets_401(client):
    assert client.get("/api/v1/admin/me").status_code == 401


async def test_logged_non_staff_gets_403(client):
    client.cookies.set("bsbr_user_session", cookie_value("76561198000000999"))
    assert client.get("/api/v1/admin/me").status_code == 403


async def test_staff_session_authorizes(client):
    await _add_staff(role="staff")
    client.cookies.set("bsbr_user_session", cookie_value(STEAM_ID))
    r = client.get("/api/v1/admin/me")
    assert r.status_code == 200
    body = r.json()
    assert body["ss_id"] == STEAM_ID
    assert body["role"] == "staff"


async def test_admin_me_via_token_fallback(client):
    r = client.get("/api/v1/admin/me", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 200
    assert r.json()["role"] == "owner"


async def test_list_and_add_remove_staff(client):
    await _add_staff(role="owner")  # owner padrão
    headers = {"X-Admin-Token": "test-token"}

    r = client.get("/api/v1/admin/staff", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1

    # adiciona um staff novo
    r = client.post(
        "/api/v1/admin/staff",
        json={"ss_id": "76561198000000002", "role": "staff"},
        headers=headers,
    )
    assert r.status_code == 200
    member_id = r.json()["id"]

    # lista com os dois
    assert len(client.get("/api/v1/admin/staff", headers=headers).json()["items"]) == 2

    # remove o staff novo
    assert client.delete(f"/api/v1/admin/staff/{member_id}", headers=headers).status_code == 200
    assert len(client.get("/api/v1/admin/staff", headers=headers).json()["items"]) == 1


async def test_cannot_remove_last_owner(client):
    await _add_staff(role="owner")
    headers = {"X-Admin-Token": "test-token"}
    members = client.get("/api/v1/admin/staff", headers=headers).json()["items"]
    owner = next(m for m in members if m["role"] == "owner")
    assert client.delete(f"/api/v1/admin/staff/{owner['id']}", headers=headers).status_code == 422


async def test_non_owner_cannot_manage_staff(client):
    await _add_staff(role="owner")
    await _add_staff("76561198000000002", role="staff")
    client.cookies.set("bsbr_user_session", cookie_value("76561198000000002"))
    # staff (não-owner) não pode adicionar/remover membros
    r = client.post("/api/v1/admin/staff", json={"ss_id": "76561198000000003"}, )
    assert r.status_code == 403


async def test_add_staff_rejects_bad_ssid(client):
    await _add_staff(role="owner")
    headers = {"X-Admin-Token": "test-token"}
    r = client.post("/api/v1/admin/staff", json={"ss_id": "123"}, headers=headers)
    assert r.status_code == 422
    # duplicado
    r = client.post("/api/v1/admin/staff", json={"ss_id": STEAM_ID}, headers=headers)
    assert r.status_code == 409
