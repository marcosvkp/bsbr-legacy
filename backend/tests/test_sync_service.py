"""Testes do serviço de sync (ScoreSaber → banco) com cliente falso."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import Difficulty, Map, Player, Score
from app.services.beatleader_resolve import clear_cache
from app.services.pp_engine import decompose_pp, get_pp
from app.services.sync import (
    parse_beatleader_score,
    parse_leaderboard_score,
    sync_difficulty_scores,
    sync_difficulty_scores_beatleader,
)


class FakeScoreSaberClient:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads

    async def leaderboard_scores_by_id(self, leaderboard_id, *, country=None, max_pages=None):
        return self.payloads

    async def close(self):
        pass


def raw_score(ss_id: str, name: str, base: int, modified: int, pp: float, time_set: str, *, modifiers: str = "", avatar: str = ""):
    return {
        "baseScore": base,
        "modifiedScore": modified,
        "modifiers": modifiers,
        "fullCombo": True,
        "rank": 1,
        "timeSet": time_set,
        "leaderboardPlayerInfo": {
            "id": ss_id,
            "name": name,
            "country": "BR",
            "pp": pp,
            "profilePicture": avatar,
        },
    }


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


@pytest.fixture
async def difficulty_id(session):
    m = Map(hash="abc123", name="Test Map", status="ranked")
    session.add(m)
    await session.flush()
    d = Difficulty(
        map_id=m.id,
        characteristic="Standard",
        name="ExpertPlus",
        max_score=1_000_000,
        total_stars=5.0,
        acc_stars=1.0,
        tech_stars=3.0,
        speed_stars=1.0,
        ss_leaderboard_id="424242",
        ranked_at=datetime.now(timezone.utc),
    )
    session.add(d)
    await session.commit()
    return d.id


PAYLOADS = [
    raw_score("76561198000000001", "Alice", 950_000, 950_000, 8000, "2026-08-20T12:00:00+00:00", avatar="https://cdn.scoresaber.com/avatars/1.jpg"),
    raw_score("76561198000000002", "Bob", 920_000, 920_000, 7000, "2026-08-20T13:00:00+00:00", avatar="https://cdn.scoresaber.com/avatars/2.jpg"),
    raw_score("76561198000000001", "Alice", 900_000, 900_000, 6000, "2026-08-21T10:00:00+00:00", avatar="https://cdn.scoresaber.com/avatars/1.jpg"),
    raw_score("76561198000000003", "NoFail", 990_000, 990_000, 9000, "2026-08-21T11:00:00+00:00", modifiers="NF"),
    raw_score("76561198000000004", "ZeroBase", 0, 0, 0, "2026-08-21T11:30:00+00:00"),
]


async def test_parse_skips_nf_and_zero():
    assert parse_leaderboard_score(PAYLOADS[3], 1_000_000) is None  # NF
    assert parse_leaderboard_score(PAYLOADS[4], 1_000_000) is None  # base 0
    ok = parse_leaderboard_score(PAYLOADS[0], 1_000_000)
    assert ok["acc"] == pytest.approx(0.95)
    assert ok["score"] == 950_000


async def test_sync_inserts_and_computes_pp(session, difficulty_id):
    stats = await sync_difficulty_scores(session, difficulty_id, client=FakeScoreSaberClient(PAYLOADS))
    assert stats.fetched == 5
    assert stats.skipped_nf == 2
    assert stats.inserted == 2  # Alice (1º payload) + Bob
    assert stats.updated == 1  # 2º payload da Alice substitui o 1º
    assert not stats.errors

    rows = (await session.scalars(select(Score))).all()
    assert len(rows) == 2  # 1 score por jogador na dificuldade
    alice = [r for r in rows if r.acc == pytest.approx(0.90)]
    assert alice and alice[0].pp > 0
    expected = decompose_pp(5.0, 90.0, share_acc=0.2, share_tech=0.6, share_speed=0.2)
    assert alice[0].pp == pytest.approx(expected["pp_total"])
    assert alice[0].pp_tech == pytest.approx(expected["pp_tech"])
    assert alice[0].pp_speed == pytest.approx(expected["pp_speed"])
    # curva do legado intacta: pp_total == get_pp(5.0, 90.0)
    assert alice[0].pp == pytest.approx(get_pp(5.0, 90.0))
    # players criados com avatar do payload do score
    players = (await session.scalars(select(Player))).all()
    assert {p.name for p in players} >= {"Alice", "Bob"}
    alice_player = next(p for p in players if p.name == "Alice")
    assert alice_player.avatar_url == "https://cdn.scoresaber.com/avatars/1.jpg"
    assert alice_player.country == "BR"


async def test_sync_idempotent(session, difficulty_id):
    fake = FakeScoreSaberClient(PAYLOADS)
    first = await sync_difficulty_scores(session, difficulty_id, client=fake)
    second = await sync_difficulty_scores(session, difficulty_id, client=fake)
    assert first.inserted == 2
    assert first.updated == 1
    assert second.inserted == 0
    assert second.updated == 3


async def test_sync_requires_leaderboard_id(session, difficulty_id):
    d = await session.get(Difficulty, difficulty_id)
    d.ss_leaderboard_id = None
    await session.commit()
    stats = await sync_difficulty_scores(session, difficulty_id, client=FakeScoreSaberClient(PAYLOADS))
    assert stats.errors and "ss_leaderboard_id" in stats.errors[0]
    assert (await session.scalars(select(Score))).first() is None


# ── BeatLeader ─────────────────────────────────────────────────────────────

class FakeBeatLeaderClient:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.calls: list[str] = []

    async def leaderboard_scores(self, leaderboard_id, *, country="BR", page=1, count=100):
        self.calls.append(f"lb:{leaderboard_id}:page{page}")
        if page > 1:
            return []
        return self.payloads

    async def player_full(self, player_id: str) -> dict | None:
        self.calls.append(f"full:{player_id}")
        return {"id": player_id, "name": "Ren93", "country": "BR", "platform": "steam"}

    async def close(self):
        pass


def bl_raw_score(bl_id: str, name: str, base: int, modified: int, acc: float, timepost: int, *, modifiers: str = ""):
    return {
        "id": 999,
        "playerId": bl_id,
        "player": {"id": bl_id, "name": name},
        "baseScore": base,
        "modifiedScore": modified,
        "accuracy": acc,
        "rank": 1,
        "modifiers": modifiers,
        "fullCombo": True,
        "timepost": timepost,
    }


def test_parse_beatleader_score():
    item = parse_beatleader_score(bl_raw_score("76561199113852020", "Ren93", 500000, 500000, 0.9, 1788000000))
    assert item is not None
    assert item["bl_player_id"] == "76561199113852020"
    assert item["acc"] == pytest.approx(0.9)
    assert item["time_set"] == datetime.fromtimestamp(1788000000, tz=timezone.utc).replace(tzinfo=None)

    # NF é ignorado; acc 0.0 vira None
    assert parse_beatleader_score(bl_raw_score("1", "A", 1, 1, 0.5, 1, modifiers="NF")) is None
    nf = parse_beatleader_score(bl_raw_score("1", "A", 100, 100, 0.0, 1))
    assert nf is not None and nf["acc"] is None


async def test_sync_beatleader_resolves_and_persists(session):
    """Batch BL: resolve player (Steam direto) e persiste score com PP do BSBR."""
    clear_cache()
    m = Map(hash="bl123", name="BL Map", status="ranked")
    session.add(m)
    await session.flush()
    d = Difficulty(
        map_id=m.id,
        characteristic="Standard",
        name="ExpertPlus",
        ss_leaderboard_id="111",
        bl_leaderboard_id="222",
        total_stars=5.0,
        acc_stars=1.5,
        tech_stars=1.5,
        speed_stars=2.0,
    )
    session.add(d)
    await session.commit()

    steam = "76561199113852020"
    fake = FakeBeatLeaderClient([bl_raw_score(steam, "Ren93", 500000, 500000, 0.9, 1788000000)])
    stats = await sync_difficulty_scores_beatleader(session, d.id, client=fake)
    assert stats.inserted == 1
    # busca scores + perfil BL para enriquecimento do player
    assert fake.calls == ["lb:222:page1", "full:76561199113852020"]

    player = (await session.scalars(select(Player).where(Player.bl_id == steam))).first()
    assert player is not None and player.ss_id == steam
    score = (await session.scalars(select(Score))).one()
    assert score.difficulty_id == d.id
    assert score.acc == pytest.approx(0.9)
    # PP é do motor BSBR (curva), não do payload
    assert score.pp == pytest.approx(get_pp(5.0, 90.0))


async def test_sync_beatleader_conflict_keeps_best_pp(session):
    """SS insere acc 0.95 (pp alto); BL acc 0.80 (pp baixo) não sobrescreve."""
    clear_cache()
    m = Map(hash="bl9", name="Conflito", status="ranked")
    session.add(m)
    await session.flush()
    d = Difficulty(
        map_id=m.id,
        characteristic="Standard",
        name="ExpertPlus",
        ss_leaderboard_id="111",
        bl_leaderboard_id="222",
        total_stars=5.0,
        acc_stars=1.5,
        tech_stars=1.5,
        speed_stars=2.0,
    )
    session.add(d)
    await session.commit()

    steam = "76561199113852020"
    fake_ss = FakeScoreSaberClient([raw_score(steam, "Ren93", 475000, 475000, 300.0, "2026-08-29T00:00:00Z")])
    # acc do SS: 475000/maxScore(500000) = 0.95
    d.max_score = 500000
    await session.commit()
    await sync_difficulty_scores(session, d.id, client=fake_ss)

    fake_bl = FakeBeatLeaderClient([bl_raw_score(steam, "Ren93", 400000, 400000, 0.80, 1788000000)])
    await sync_difficulty_scores_beatleader(session, d.id, client=fake_bl)

    scores = (await session.scalars(select(Score))).all()
    assert len(scores) == 1
    assert scores[0].acc == pytest.approx(0.95)  # SS (maior PP) permanece
