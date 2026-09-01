"""Testes do serviço de ranking (agregação 0.965, ranks, snapshots, medalhas)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import Difficulty, Map, Player, RankSnapshot, Score
from app.services.ranking import (
    iso_week,
    medal_from_rank,
    medals_for_player,
    recompute_all_rankings,
    recompute_player,
    write_weekly_snapshot,
)


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


async def seed(session, *, ranked: bool = True):
    m = Map(hash="h1", name="Mapa", status="ranked" if ranked else "candidate")
    session.add(m)
    await session.flush()
    d = Difficulty(
        map_id=m.id,
        characteristic="Standard",
        name="ExpertPlus",
        total_stars=5.0,
        acc_stars=5.0,
        tech_stars=0.0,
        speed_stars=0.0,
        max_score=1000000,
    )
    session.add(d)
    await session.flush()
    p1 = Player(ss_id="p1", name="Top")
    p2 = Player(ss_id="p2", name="Mid")
    session.add_all([p1, p2])
    await session.flush()

    def score(pid: int, pp: float, rank: int, minute: int) -> Score:
        return Score(
            player_id=pid,
            difficulty_id=d.id,
            score=900000,
            acc=0.95,
            pp=pp,
            pp_acc=pp * 0.2,
            pp_tech=pp * 0.6,
            pp_speed=pp * 0.2,
            leaderboard_rank=rank,
            time_set=datetime(2026, 8, 20, 12, minute, tzinfo=timezone.utc).replace(tzinfo=None),
        )

    # Top: dois scores (100 e 50) → weighted = 100 + 50*0.965 = 148.25
    session.add_all(
        [
            score(p1.id, 100.0, 1, 0),
            score(p1.id, 50.0, 2, 30),
            score(p2.id, 80.0, 3, 45),
        ]
    )
    await session.commit()
    return p1.id, p2.id


def test_medal_table():
    assert [medal_from_rank(r) for r in range(1, 9)] == [10, 8, 6, 5, 4, 3, 2, 1]
    assert medal_from_rank(10) == 1


async def test_recompute_orders_and_weights(session):
    p1, p2 = await seed(session)
    summary = await recompute_all_rankings(session)
    assert summary.players_updated == 2

    top = await session.get(Player, p1)
    mid = await session.get(Player, p2)
    assert top.pp_total == pytest.approx(148.25)  # 100 + 50×0.965
    assert mid.pp_total == pytest.approx(80.0)
    assert top.rank == 1 and mid.rank == 2
    # componentes agregados na mesma ordem do total
    assert top.pp_tech == pytest.approx((100 * 0.6) + (50 * 0.6) * 0.965)


async def test_unranked_maps_excluded(session):
    p1, _ = await seed(session, ranked=False)
    summary = await recompute_all_rankings(session)
    assert summary.players_updated == 0
    player = await session.get(Player, p1)
    assert player.pp_total == 0.0
    assert player.rank is None


async def test_snapshot_idempotent_per_week(session):
    _, _ = await seed(session)
    await recompute_all_rankings(session)
    week = iso_week()
    n1 = await write_weekly_snapshot(session, week)
    n2 = await write_weekly_snapshot(session, week)  # segunda escrita substitui
    assert n1 == n2 == 2
    rows = (await session.scalars(select(RankSnapshot))).all()
    assert len(rows) == 2


async def test_medals_sum_per_map(session):
    p1, _ = await seed(session)  # p1 tem ranks 1 e 2 na MESMA dificuldade → best=1
    medals = await medals_for_player(session, p1)
    assert medals["total"] == 10  # melhor posição por mapa: apenas o 1º lugar conta
    assert medals["best_rank"] == 1


async def test_recompute_player_updates_only_that_player(session):
    p1, p2 = await seed(session)  # p1: 100+50 → 148.25; p2: 80
    await recompute_all_rankings(session)  # estado base: ambos com pp/rank

    # Novo score chega (ingest ao vivo) — só p1 é recalculado, p2 intacto.
    d_id = (await session.scalars(select(Difficulty))).first().id
    session.add(
        Score(
            player_id=p1,
            difficulty_id=d_id,
            score=950000,
            acc=0.95,
            pp=60.0,
            pp_acc=12.0,
            pp_tech=36.0,
            pp_speed=12.0,
            leaderboard_rank=1,
            time_set=datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc).replace(tzinfo=None),
        )
    )
    await session.commit()

    await recompute_player(session, p1)

    top = await session.get(Player, p1)
    mid = await session.get(Player, p2)
    # ordenado desc: 100 + 60×0.965 + 50×0.965²
    assert top.pp_total == pytest.approx(100 + 60 * 0.965 + 50 * 0.965**2)
    assert top.rank == 1
    assert mid.pp_total == pytest.approx(80.0)  # intocado
    assert mid.rank == 2  # rank re-atribuído globalmente, consistente
