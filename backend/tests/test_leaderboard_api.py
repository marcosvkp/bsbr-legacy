"""Testes do endpoint GET /api/v1/leaderboard/{hash} — top scores por dificuldade.

Este endpoint alimenta o painel in-game do plugin BSBR (leaderboard da
dificuldade selecionada). O hash chega em MAIÚSCULAS (custom_level_<HASH>) e
é normalizado para lowercase no backend.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import Base
from app.main import app
from app.models import Difficulty, Map, MapStatus, Player, Score
from app.services.pp_engine import get_pp


@pytest.fixture(autouse=True)
def _admin_token():
    get_settings().admin_token = "test-token"
    yield
    get_settings().admin_token = None


@pytest.fixture
async def client(tmp_path, monkeypatch):
    # engine global apontado para sqlite temporário ANTES do TestClient abrir lifespan
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/lb.db")
    import app.core.db as dbmod

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/lb.db")
    dbmod.engine = engine
    dbmod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    await engine.dispose()


async def _seed(
    *,
    map_hash: str = "abc123",
    difficulty_name: str = "ExpertPlus",
    players: list[tuple[str, str]] = None,  # (ss_id, name)
    scores: list[tuple[str, str, float]] = (),  # (ss_id, difficulty_name, pp)
    is_ranked: bool = True,
):
    from app.core.db import SessionLocal

    players = players or [("ss1", "Alice"), ("ss2", "Bob"), ("ss3", "Carol")]
    async with SessionLocal() as s:
        m = Map(hash=map_hash, name="Mapa", status=MapStatus.RANKED, mapper="Mapper")
        s.add(m)
        await s.flush()
        d = Difficulty(
            map_id=m.id,
            characteristic="Standard",
            name=difficulty_name,
            total_stars=5.0,
            acc_stars=2.5,
            tech_stars=1.5,
            speed_stars=1.0,
            max_score=1_000_000,
            is_ranked=is_ranked,
            ranked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        s.add(d)
        await s.flush()
        pid_by_ss = {}
        for ss_id, name in players:
            p = Player(ss_id=ss_id, name=name, country="BR")
            s.add(p)
            await s.flush()
            pid_by_ss[ss_id] = p.id
        for ss_id, _diff, pp in scores:
            s.add(
                Score(
                    player_id=pid_by_ss[ss_id],
                    difficulty_id=d.id,
                    score=int(pp * 100),
                    acc=round(pp / 100, 4),
                    pp=pp,
                    leaderboard_rank=1,
                    time_set=datetime(2026, 8, 20, 12, 0),
                )
            )
        await s.commit()
    return m.hash


async def test_leaderboard_returns_top_scores_by_pp(client):
    await _seed(
        scores=[
            ("ss1", "ExpertPlus", get_pp(5.0, 95.0)),
            ("ss2", "ExpertPlus", get_pp(5.0, 90.0)),
            ("ss3", "ExpertPlus", get_pp(5.0, 85.0)),
        ]
    )
    r = client.get("/api/v1/leaderboard/ABC123?difficulty=ExpertPlus")  # hash uppercase
    assert r.status_code == 200
    body = r.json()
    assert body["hash"] == "abc123"  # normalizado p/ lowercase
    assert body["map_name"] == "Mapa"
    assert body["difficulty"] == "ExpertPlus"
    assert body["total_stars"] == 5.0
    names = [s["player_name"] for s in body["scores"]]
    assert names == ["Alice", "Bob", "Carol"]  # pp desc
    assert [s["rank"] for s in body["scores"]] == [1, 2, 3]
    assert body["scores"][0]["pp"] == pytest.approx(get_pp(5.0, 95.0), abs=1e-2)
    assert body["player"] is None  # sem player_id


async def test_leaderboard_honors_limit(client):
    await _seed(
        scores=[
            ("ss1", "ExpertPlus", get_pp(5.0, 95.0)),
            ("ss2", "ExpertPlus", get_pp(5.0, 90.0)),
            ("ss3", "ExpertPlus", get_pp(5.0, 85.0)),
        ]
    )
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&limit=2")
    assert r.status_code == 200
    assert len(r.json()["scores"]) == 2


async def test_leaderboard_map_not_found(client):
    r = client.get("/api/v1/leaderboard/nope123?difficulty=ExpertPlus")
    assert r.status_code == 404


async def test_leaderboard_difficulty_not_ranked_empty(client):
    # hash único: evita cache de memória de teste anterior com o mesmo hash
    await _seed(map_hash="unranked1", is_ranked=False)
    r = client.get("/api/v1/leaderboard/unranked1?difficulty=ExpertPlus")
    assert r.status_code == 404  # difficulty não rankeada não existe p/ o painel


async def test_leaderboard_unknown_difficulty_404(client):
    await _seed()
    r = client.get("/api/v1/leaderboard/abc123?difficulty=Hard")
    assert r.status_code == 404


async def test_leaderboard_player_rank_when_has_score(client):
    await _seed(
        scores=[
            ("ss1", "ExpertPlus", get_pp(5.0, 95.0)),
            ("ss2", "ExpertPlus", get_pp(5.0, 90.0)),
            ("ss3", "ExpertPlus", get_pp(5.0, 85.0)),
        ]
    )
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&player_id=ss2")
    body = r.json()
    assert body["player"] == {
        "ss_id": "ss2",
        "name": "Bob",
        "rank": 2,  # 1-based, atrás apenas da Alice
    }


async def test_leaderboard_player_rank_top_one(client):
    await _seed(
        scores=[("ss1", "ExpertPlus", get_pp(5.0, 95.0))]
    )
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&player_id=ss1")
    assert r.json()["player"]["rank"] == 1


async def test_leaderboard_player_null_when_no_score(client):
    await _seed(
        scores=[("ss1", "ExpertPlus", get_pp(5.0, 95.0))]
    )
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&player_id=ss2")
    assert r.status_code == 200
    assert r.json()["player"] is None  # ss2 não tem score nessa dificuldade


async def test_leaderboard_player_rank_survives_cache(client):
    """O rank do player é calculado por request (fora do cache): mesmo depois
    de uma chamada cacheada, player_id distinto resolve corretamente."""
    await _seed(
        scores=[
            ("ss1", "ExpertPlus", get_pp(5.0, 95.0)),
            ("ss2", "ExpertPlus", get_pp(5.0, 90.0)),
        ]
    )
    # primeira chamada popula o cache sem player
    assert client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus").json()["player"] is None
    # segunda chamada (cache hit) ainda calcula o player do ss3 (sem score → None)
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&player_id=ss3")
    assert r.json()["player"] is None
    # e do ss1 (com score → rank 1)
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&player_id=ss1")
    assert r.json()["player"]["rank"] == 1


async def test_leaderboard_pagination_total_and_has_more(client):
    """offset/limit paginam; total/has_more alimentam as setas do painel."""
    await _seed(
        scores=[
            (f"ss{i}", "ExpertPlus", get_pp(5.0, 90.0 + i)) for i in range(1, 4)
        ]
    )
    # página 1: top 2 (maior pp), tem mais
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&limit=2&offset=0")
    body = r.json()
    assert [s["rank"] for s in body["scores"]] == [1, 2]
    assert body["total"] == 3
    assert body["has_more"] is True
    # página 2: o restante, sem mais
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&limit=2&offset=2")
    body = r.json()
    assert [s["rank"] for s in body["scores"]] == [3]
    assert body["has_more"] is False
    # página além do fim: vazio
    r = client.get("/api/v1/leaderboard/abc123?difficulty=ExpertPlus&limit=2&offset=5")
    body = r.json()
    assert body["scores"] == []
    assert body["total"] == 3
    assert body["has_more"] is False


async def test_leaderboard_rank_is_global_not_page_local(client):
    """Com offset, o rank da linha é a posição global (offset + idx + 1)."""
    # hash único: evita cache de memória de teste anterior (mesma chave limit:offset)
    await _seed(
        map_hash="pagglobal1",
        scores=[
            ("ss1", "ExpertPlus", get_pp(5.0, 95.0)),
            ("ss2", "ExpertPlus", get_pp(5.0, 90.0)),
            ("ss3", "ExpertPlus", get_pp(5.0, 85.0)),
        ]
    )
    r = client.get("/api/v1/leaderboard/pagglobal1?difficulty=ExpertPlus&limit=2&offset=2")
    body = r.json()
    assert [s["rank"] for s in body["scores"]] == [3]
    assert body["scores"][0]["player_name"] == "Carol"
