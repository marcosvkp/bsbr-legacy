"""Testes do scorefeed ao vivo: parsers, persistência e endpoint /live/recent."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import Difficulty, Map, MapStatus, Player, Score
from app.services.live.bus import recent_scores
from app.services.live.messages import parse_message
from app.services.live.persist import persist_live_score


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/live.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


def test_parse_scoresaber_real_payload():
    """Payload real capturado do feed (2026-08-28): commandName/commandData."""
    raw = {
        "commandName": "score",
        "commandData": {
            "score": {
                "id": 93593687,
                "leaderboardPlayerInfo": {
                    "id": "7656119812345678",
                    "name": "Seaspooder",
                    "country": "US",
                },
                "rank": 301,
                "baseScore": 569213,
                "modifiedScore": 569213,
                "pp": 0,
                "modifiers": "",
                "fullCombo": False,
                "timeSet": "2026-08-28T04:07:23.351Z",
            },
            "leaderboard": {
                "id": 695986,
                "songHash": "69805A8DEB951713842EE24B7F016634E8201E08",
                "songName": "Tic! Tac! Toe!",
                "maxScore": 790395,
                "difficulty": {"difficulty": 9, "difficultyRaw": "_ExpertPlus_SoloStandard"},
            },
        },
    }
    live = parse_message("scoresaber", raw)
    assert live is not None
    assert live.score_id == "93593687"
    assert live.leaderboard_id == "695986"
    assert live.player_id == "7656119812345678"
    assert live.player_name == "Seaspooder"
    assert live.player_country == "US"
    assert live.song_hash == "69805A8DEB951713842EE24B7F016634E8201E08"
    assert live.difficulty == "ExpertPlus"
    assert live.score == 569213
    assert live.acc == pytest.approx(569213 / 790395)
    assert live.pp is None  # pp=0 no feed -> None (calculado pela curva BSBR)
    assert live.full_combo is False
    assert live.rank == 301
    assert live.time_set == datetime(2026, 8, 28, 4, 7, 23, 351000)


def test_parse_scoresaber_legacy_format():
    """Formato antigo {"command":"score","data":{...}} continua suportado."""
    raw = {
        "command": "score",
        "data": {
            "id": 12345,
            "playerId": 7656119812345678,
            "playerName": "Jogador BR",
            "leaderboardId": 999,
            "songHash": "abc123",
            "difficulty": 9,
            "score": 950000,
            "unmodififiedScore": 900000,
            "maxScore": 1000000,
            "acc": 0.9,
            "pp": 430.12,
            "mods": "NF",
            "rank": 3,
            "timeSet": "2026-08-28T03:00:00Z",
        },
    }
    live = parse_message("scoresaber", raw)
    assert live is not None
    assert live.score_id == "12345"
    assert live.leaderboard_id == "999"
    assert live.player_id == "7656119812345678"
    assert live.player_name == "Jogador BR"
    assert live.difficulty == "ExpertPlus"
    assert live.score == 950000
    assert live.acc == pytest.approx(0.9)
    assert live.pp == pytest.approx(430.12)
    assert live.mods == "NF"
    assert live.time_set == datetime(2026, 8, 28, 3, 0, 0)


def test_parse_scoresaber_invalid_command():
    assert parse_message("scoresaber", {"command": "ping", "data": {}}) is None
    assert parse_message("scoresaber", "not json{{{") is None
    assert parse_message("scoresaber", {"command": "score", "data": {}}) is None  # sem ids
    assert parse_message("scoresaber", {"commandName": "score", "commandData": {}}) is None


def test_parse_beatleader():
    raw = {
        "command": "score",
        "data": {
            "id": 777,
            "leaderboardId": 555,
            "playerId": 123,
            "player": {"id": 123, "name": "XxPlayerxX"},
            "leaderboard": {"song": {"hash": "def456"}, "maxScore": 1000000},
            "score": 880000,
            "acc": 0.88,
            "pp": 300.5,
            "fc": True,
            "timepost": "2026-08-28T01:30:00Z",
        },
    }
    live = parse_message("beatleader", raw)
    assert live is not None
    assert live.source == "beatleader"
    assert live.player_name == "XxPlayerxX"
    assert live.song_hash == "def456"
    assert live.full_combo is True
    assert live.pp == pytest.approx(300.5)


async def test_persist_live_score_inserts_and_updates(session):
    m = Map(hash="h" * 40, name="Mapa", status=MapStatus.RANKED, mapper="M")
    session.add(m)
    await session.flush()
    d = Difficulty(
        map_id=m.id,
        characteristic="Standard",
        name="ExpertPlus",
        ss_leaderboard_id="999",
        total_stars=6.0,
        acc_stars=1.0,
        tech_stars=1.0,
        speed_stars=4.0,
        max_score=1000000,
        ranked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    session.add(d)
    await session.commit()

    from app.services.live.messages import LiveScore

    live = LiveScore(
        source="scoresaber",
        score_id="1",
        leaderboard_id="999",
        player_id="p1",
        player_name="Player Um",
        player_country="BR",
        song_hash="h" * 40,
        difficulty="ExpertPlus",
        score=900000,
        acc=0.9,
        pp=None,
        mods="",
        full_combo=False,
        max_score=1000000,
        rank=1,
        time_set=datetime(2026, 8, 28, 3, 0, 0),
    )

    outcome = await persist_live_score(session, live)
    assert "inserted" in outcome
    assert outcome["inserted"] is not None

    # player criado automaticamente com o country do payload
    player = (await session.scalars(select(Player).where(Player.ss_id == "p1"))).first()
    assert player is not None and player.name == "Player Um"
    assert player.country == "BR"

    # mesmo time_set → upsert (updated), não duplica
    live.score = 950000
    live.acc = 0.95
    outcome = await persist_live_score(session, live)
    assert "updated" in outcome
    scores = (await session.scalars(select(Score))).all()
    assert len(scores) == 1
    assert scores[0].score == 950000
    # pp calculado pela curva (acc share da dificuldade)
    assert scores[0].pp is not None and scores[0].pp > 0
    # enriquecimento do feed: hash/nome/capa do catálogo + avatar do jogador
    assert outcome["map_hash"] == "h" * 40
    assert outcome["map_name"] == "Mapa"
    assert outcome["cover_url"] is None
    assert outcome["avatar_url"] is None
    assert outcome["difficulty_name"] == "ExpertPlus"


async def test_persist_ignores_unknown_leaderboard(session):
    from app.services.live.messages import LiveScore

    live = LiveScore(
        source="scoresaber",
        score_id="1",
        leaderboard_id="desconhecido",
        player_id="p1",
        player_name="Player",
        player_country="BR",
        song_hash=None,
        difficulty=None,
        score=1,
        acc=None,
        pp=None,
        mods="",
        full_combo=False,
        max_score=None,
        rank=None,
        time_set=datetime(2026, 8, 28, 3, 0, 0),
    )
    outcome = await persist_live_score(session, live)
    assert outcome == {"ignored": "not_ranked"}
    assert (await session.scalars(select(Score))).all() == []


async def test_persist_ignores_non_br_player(session):
    """Jogador fora do Brasil não entra no feed ao vivo (mesmo em mapa rankeado)."""
    m = Map(hash="r" * 40, name="Ranked", status=MapStatus.RANKED, mapper="M")
    session.add(m)
    await session.flush()
    session.add(
        Difficulty(
            map_id=m.id,
            characteristic="Standard",
            name="ExpertPlus",
            ss_leaderboard_id="997",
            total_stars=6.0,
        )
    )
    await session.commit()

    from app.services.live.messages import LiveScore

    live = LiveScore(
        source="scoresaber",
        score_id="1",
        leaderboard_id="997",
        player_id="p1",
        player_name="Gringo",
        player_country="US",
        song_hash="r" * 40,
        difficulty="ExpertPlus",
        score=1,
        acc=None,
        pp=None,
        mods="",
        full_combo=False,
        max_score=None,
        rank=None,
        time_set=datetime(2026, 8, 28, 3, 0, 0),
    )
    outcome = await persist_live_score(session, live)
    assert outcome == {"ignored": "not_br"}
    assert (await session.scalars(select(Score))).all() == []


async def test_persist_ignores_candidate_map_with_leaderboard(session):
    """Candidato/qualificado com ss_leaderboard_id NÃO entra no feed ao vivo."""
    m = Map(hash="c" * 40, name="Candidato", status=MapStatus.CANDIDATE, mapper="M")
    session.add(m)
    await session.flush()
    session.add(
        Difficulty(
            map_id=m.id,
            characteristic="Standard",
            name="ExpertPlus",
            ss_leaderboard_id="998",
            total_stars=6.0,
        )
    )
    await session.commit()

    from app.services.live.messages import LiveScore

    live = LiveScore(
        source="scoresaber",
        score_id="1",
        leaderboard_id="998",
        player_id="p1",
        player_name="Player",
        player_country="BR",
        song_hash="c" * 40,
        difficulty="ExpertPlus",
        score=1,
        acc=None,
        pp=None,
        mods="",
        full_combo=False,
        max_score=None,
        rank=None,
        time_set=datetime(2026, 8, 28, 3, 0, 0),
    )
    outcome = await persist_live_score(session, live)
    assert outcome == {"ignored": "not_ranked"}
    assert (await session.scalars(select(Score))).all() == []


async def test_recent_scores_without_redis(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "")
    import app.services.live.bus as bus

    monkeypatch.setattr(bus, "_redis", None)
    assert await recent_scores() == []
