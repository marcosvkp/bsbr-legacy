"""Testes da qualificação (análise simulada → candidato → aprovação rankeada)."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import Difficulty, Map, MapStatus, RatingHistory
from app.services.qualification import approve_map, qualify_source


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


def fake_analysis():
    from bsbr_analyzer.analysis import DifficultyAnalysis, MapAnalysis

    diff = DifficultyAnalysis(
        characteristic="Standard",
        difficulty="ExpertPlus",
        njs=16.0,
        notes=500,
        nps=4.2,
        total_stars=6.83,
        acc_stars=1.79,
        tech_stars=1.98,
        speed_stars=3.06,
        share_acc=0.26,
        share_tech=0.29,
        share_speed=0.45,
        style_tags=["tech", "speed"],
        features={"nps": 4.2, "note_count": 500},
    )
    return MapAnalysis(
        map_id="53c5a",
        hash="a" * 40,
        name="Musica Teste",
        mapper="Mapper",
        bpm=130.0,
        difficulties=[diff],
    )


async def test_qualify_creates_candidate(session, monkeypatch):
    import bsbr_analyzer

    monkeypatch.setattr(bsbr_analyzer, "analyze_map", lambda source: fake_analysis())
    preview = await qualify_source(session, "53c5a", submitted_by="staff1")

    assert preview["created"] is True
    assert preview["map"]["status"] == "candidate"
    assert preview["map"]["hash"] == "a" * 40
    d = preview["difficulties"][0]
    assert (d["total_stars"], d["tech_stars"], d["speed_stars"]) == (6.83, 1.98, 3.06)

    m = (await session.scalars(select(Map))).one()
    assert m.beatsaver_id == "53c5a"
    diff_row = (await session.scalars(select(Difficulty))).one()
    assert diff_row.features == {"nps": 4.2, "note_count": 500}
    assert diff_row.ss_leaderboard_id is None


async def test_requalify_updates_without_duplicating(session, monkeypatch):
    import bsbr_analyzer

    monkeypatch.setattr(bsbr_analyzer, "analyze_map", lambda source: fake_analysis())
    await qualify_source(session, "53c5a")
    preview2 = await qualify_source(session, "53c5a")
    assert preview2["created"] is False
    assert len((await session.scalars(select(Map))).all()) == 1
    assert len((await session.scalars(select(Difficulty))).all()) == 1


async def test_approve_requires_leaderboard_ids(session, monkeypatch):
    import bsbr_analyzer

    monkeypatch.setattr(bsbr_analyzer, "analyze_map", lambda source: fake_analysis())
    preview = await qualify_source(session, "53c5a")
    map_id = preview["map"]["id"]

    with pytest.raises(ValueError, match="ss_leaderboard_id ausente"):
        await approve_map(session, map_id, ss_leaderboard_ids={}, reviewer="staff")

    approved = await approve_map(
        session, map_id, ss_leaderboard_ids={"ExpertPlus": "999888"}, reviewer="staff7"
    )
    assert approved.status == MapStatus.RANKED
    diff_row = (await session.scalars(select(Difficulty))).one()
    assert diff_row.ss_leaderboard_id == "999888"
    assert diff_row.ranked_at is not None

    hist = (await session.scalars(select(RatingHistory))).one()
    assert hist.total_stars_before is None and hist.total_stars_after == 6.83
    assert hist.reason.startswith("Ranqueamento inicial")


async def test_double_approve_rejected(session, monkeypatch):
    import bsbr_analyzer

    monkeypatch.setattr(bsbr_analyzer, "analyze_map", lambda source: fake_analysis())
    preview = await qualify_source(session, "53c5a")
    map_id = preview["map"]["id"]
    await approve_map(session, map_id, ss_leaderboard_ids={"ExpertPlus": "1"}, reviewer="s")
    with pytest.raises(ValueError, match="já está rankeado"):
        await approve_map(session, map_id, ss_leaderboard_ids={"ExpertPlus": "1"}, reviewer="s")
