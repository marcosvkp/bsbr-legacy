"""Testes do reweight v2: análise manual de um mapa, apply-delta e recalc imediato."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import Difficulty, Map, Player, RatingHistory, Score
from app.services.reweight.service import (
    analyze_source,
    apply_delta,
    recompute_difficulty_scores,
)


@pytest.fixture(autouse=True)
def _no_ml_network(monkeypatch):
    """Sem rede: o ML fica indisponível e a análise cai para performance/None."""
    import app.services.reweight.service as service

    async def _no_ml(map_source):
        return None

    monkeypatch.setattr(service, "_ml_stars_by_difficulty", _no_ml)


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


async def make_map(session, *, hash_="h1", name="Mapa", beatsaver_id="1abc") -> Map:
    m = Map(hash=hash_, name=name, status="ranked", beatsaver_id=beatsaver_id)
    session.add(m)
    await session.flush()
    return m


async def make_difficulty(session, map_: Map, *, name="ExpertPlus", total=5.0, acc=1.0, tech=3.0, speed=1.0) -> Difficulty:
    d = Difficulty(
        map_id=map_.id,
        characteristic="Standard",
        name=name,
        total_stars=total,
        acc_stars=acc,
        tech_stars=tech,
        speed_stars=speed,
        is_ranked=True,
        ss_leaderboard_id="12345",
        max_score=1_000_000,
    )
    session.add(d)
    await session.flush()
    return d


async def seed_scores(session, difficulty_id: int, accs: list[float]):
    """Scores com acc preenchido e pp nulo (estado pós-sync antes do recalc)."""
    p = Player(ss_id="p1", name="Jogador", pp_total=6000)
    session.add(p)
    await session.flush()
    for i, acc in enumerate(accs):
        session.add(
            Score(
                player_id=p.id,
                difficulty_id=difficulty_id,
                score=int(acc * 1_000_000),
                acc=acc,
                ss_player_pp=5000.0,
                full_combo=True,
                leaderboard_rank=i + 1,
                time_set=datetime(2026, 8, day=20, hour=12, minute=i % 60, second=i // 60),
            )
        )
    await session.commit()


async def test_recompute_difficulty_scores_updates_pp(session):
    map_ = await make_map(session)
    d = await make_difficulty(session, map_, total=5.0)
    await seed_scores(session, d.id, [0.95, 0.90])
    await session.commit()

    # antes do recalc os scores não têm PP (pp NULL)
    rows = (await session.scalars(select(Score))).all()
    assert all(r.pp is None for r in rows)

    updated = await recompute_difficulty_scores(session, d.id)
    assert updated == 2

    rows = (await session.scalars(select(Score).order_by(Score.acc.desc()))).all()
    # pp total = stars * STAR_MULTIPLIER * mod(acc) — só checar que foi preenchido
    assert all(r.pp is not None and r.pp > 0 for r in rows)
    assert rows[0].pp > rows[1].pp  # acc maior → pp maior
    # sub-PPs somam o total (decomposição normalizada)
    assert rows[0].pp_acc + rows[0].pp_tech + rows[0].pp_speed == pytest.approx(rows[0].pp)


async def test_apply_delta_recals_scores_and_players(session):
    map_ = await make_map(session)
    d = await make_difficulty(session, map_, total=5.0, acc=1.0, tech=3.0, speed=1.0)
    await seed_scores(session, d.id, [0.95])
    await session.commit()

    result = await apply_delta(session, d.id, delta_stars=0.5, reviewer="staff42")
    assert result["old_stars"] == 5.0
    assert result["new_stars"] == pytest.approx(5.5)
    assert result["scores_updated"] == 1
    assert result["players_affected"] == 1

    await session.refresh(d)
    assert d.total_stars == pytest.approx(5.5)
    # sub-stars reescalados pelo fator 5.5/5.0
    assert d.tech_stars == pytest.approx(round(3.0 * 1.1, 2))

    # RatingHistory registrado (auditoria)
    hist = (await session.scalars(select(RatingHistory))).first()
    assert hist is not None
    assert hist.applied_by == "staff42"
    assert hist.total_stars_before == 5.0 and hist.total_stars_after == pytest.approx(5.5)

    # scores recalculados com as novas stars (pp subiu proporcionalmente)
    row = (await session.scalars(select(Score))).one()
    assert row.pp is not None and row.pp > 0


async def test_apply_delta_rejects_invalid_difficulty(session):
    with pytest.raises(ValueError):
        await apply_delta(session, 999, delta_stars=0.5, reviewer="staff")


async def test_analyze_source_by_map_id(session):
    map_ = await make_map(session)
    d = await make_difficulty(session, map_, total=5.0)
    await seed_scores(session, d.id, [0.91] * 40)  # confiança média
    await session.commit()

    result = await analyze_source(session, map_id=map_.id)
    assert result["map"]["id"] == map_.id
    assert len(result["difficulties"]) == 1
    item = result["difficulties"][0]
    assert item["difficulty_id"] == d.id
    assert item["current_stars"] == 5.0
    # performance: acc observada 91% vs esperada 90.5% → nerf (delta negativo)
    assert item["perf_delta"] is not None and item["perf_delta"] < 0
    assert item["confidence"] == "medium"
    assert item["sample_size"] == 40


async def test_analyze_source_by_beatsaver_id(session):
    map_ = await make_map(session, beatsaver_id="abc123")
    d = await make_difficulty(session, map_, total=6.0)
    await seed_scores(session, d.id, [0.95] * 120)  # confiança alta
    await session.commit()

    result = await analyze_source(session, source="abc123")
    assert result["map"]["beatsaver_id"] == "abc123"
    item = result["difficulties"][0]
    assert item["confidence"] == "high"


async def test_analyze_source_unknown_raises(session):
    with pytest.raises(ValueError):
        await analyze_source(session, source="nao-existe")


async def test_analyze_source_difficulty_without_scores_ml_only(session):
    """Dificuldade não rankeada / sem scores → confidence none, sem perf_delta."""
    map_ = await make_map(session)
    d = Difficulty(
        map_id=map_.id,
        characteristic="Standard",
        name="Easy",
        total_stars=2.0,
        acc_stars=1.0,
        tech_stars=1.0,
        speed_stars=0.0,
        is_ranked=False,
    )
    session.add(d)
    await session.commit()

    result = await analyze_source(session, map_id=map_.id)
    item = result["difficulties"][0]
    assert item["is_ranked"] is False
    assert item["confidence"] == "none"
    assert item["perf_delta"] is None
