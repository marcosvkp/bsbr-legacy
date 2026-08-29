"""Testes do resolver de contas BeatLeader → ScoreSaber."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import Player
from app.services.beatleader_resolve import (
    clear_cache,
    extract_ss_id_from_socials,
    resolve_bl_player,
)


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/resolve.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


class FakeClient:
    """Simula o BeatLeaderClient: player_full e search_players."""

    def __init__(self, players: dict[str, dict], search: list[dict] | None = None) -> None:
        self._players = players
        self._search = search or []
        self.calls: list[str] = []

    async def player_full(self, player_id: str) -> dict | None:
        self.calls.append(f"full:{player_id}")
        return self._players.get(player_id)

    async def search_players(self, search: str, country: str | None = "BR") -> list[dict]:
        self.calls.append(f"search:{search}")
        return self._search


def test_extract_ss_id_from_socials_scoresaber_link():
    socials = [
        {"service": "Discord", "link": "https://discordapp.com/users/1", "userId": "1"},
        {"service": "ScoreSaber", "link": "https://scoresaber.com/u/7656119812345678", "userId": ""},
    ]
    assert extract_ss_id_from_socials(socials) == "7656119812345678"


def test_extract_ss_id_from_socials_returns_none():
    socials = [{"service": "Discord", "link": "https://discordapp.com/users/1", "userId": "1"}]
    assert extract_ss_id_from_socials(socials) is None
    assert extract_ss_id_from_socials(None) is None


async def test_resolve_steam_id_direct(session):
    """bl_id = Steam ID (17 dígitos) → ss_id = bl_id, sem chamada de API."""
    clear_cache()
    client = FakeClient({})
    player = await resolve_bl_player(session, "76561199113852020", client, player_name="Ren93")
    assert player.ss_id == "76561199113852020"
    assert player.bl_id == "76561199113852020"
    assert player.bl_resolved_at is not None
    assert client.calls == []  # não precisou da API


async def test_resolve_via_socials(session):
    """bl_id não-Steam: vínculo via socials do ScoreSaber."""
    clear_cache()
    bl_id = "30002523"  # id numérico curto (não-Steam)
    client = FakeClient(
        {
            bl_id: {
                "id": bl_id,
                "platform": "oculus",
                "linkedIds": None,
                "socials": [
                    {"service": "ScoreSaber", "link": "https://scoresaber.com/u/7656119888888888", "userId": ""},
                ],
            }
        }
    )
    player = await resolve_bl_player(session, bl_id, client, player_name="sotarks")
    assert player.ss_id == "7656119888888888"
    assert player.bl_id == bl_id
    assert player.bl_resolved_at is not None
    assert "full:30002523" in client.calls


async def test_resolve_creates_player_without_link(session):
    """Sem vínculo: cria Player com bl_id e ss_id provisórios (batch tenta depois)."""
    clear_cache()
    bl_id = "999999"
    client = FakeClient({bl_id: {"id": bl_id, "platform": "oculus", "socials": []}})
    player = await resolve_bl_player(session, bl_id, client, player_name="SemLink")
    assert player.bl_id == bl_id
    assert player.ss_id == bl_id  # provisório
    assert player.bl_resolved_at is None


async def test_resolve_reuses_existing_player(session):
    """Já existe Player com bl_id → retorna sem chamar API."""
    clear_cache()
    existing = Player(ss_id="76561199113852020", name="Ren93", bl_id="76561199113852020")
    session.add(existing)
    await session.commit()

    client = FakeClient({})
    player = await resolve_bl_player(session, "76561199113852020", client)
    assert player is existing
    assert client.calls == []


async def test_resolve_unifies_with_ss_player(session):
    """Player SS já existe: resolver BL encontra o mesmo humano e une (bl_id setado)."""
    clear_cache()
    ss = Player(ss_id="76561199113852020", name="Ren93", country="BR")
    session.add(ss)
    await session.commit()

    client = FakeClient({})
    player = await resolve_bl_player(session, "76561199113852020", client, player_name="Ren93")
    assert player is ss
    assert player.bl_id == "76561199113852020"
    assert player.bl_resolved_at is not None
    assert (await session.scalars(select(Player))).all() == [ss]  # sem duplicar
