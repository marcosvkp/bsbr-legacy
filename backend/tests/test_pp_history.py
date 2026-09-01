"""Testes da série de progressão de PP por timestamp dos scores (pp_history)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import Difficulty, Map, MapStatus, Player, Score
from app.services.pp_history import (
    DEFAULT_DAYS,
    ESTIMATE_GAP_DAYS,
    MAX_DAYS,
    MIN_DAYS,
    build_pp_history,
)


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/pp_history.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def seed(session, *, times, pps):
    """Cria um mapa rankeado e um jogador com scores nos tempos/pps dados."""
    m = Map(hash="h" * 40, name="Mapa", status=MapStatus.RANKED, mapper="M")
    session.add(m)
    await session.flush()
    d = Difficulty(
        map_id=m.id,
        characteristic="Standard",
        name="ExpertPlus",
        total_stars=6.0,
        acc_stars=1.0,
        tech_stars=1.0,
        speed_stars=4.0,
        max_score=1000000,
    )
    session.add(d)
    await session.flush()
    p = Player(ss_id="p1", name="Player")
    session.add(p)
    await session.flush()
    for ts, pp in zip(times, pps):
        session.add(
            Score(
                player_id=p.id,
                difficulty_id=d.id,
                score=900000,
                acc=0.9,
                pp=pp,
                pp_acc=pp * 0.2,
                pp_tech=pp * 0.6,
                pp_speed=pp * 0.2,
                leaderboard_rank=1,
                time_set=ts,
            )
        )
    await session.commit()
    p.pp_total = 0.0  # atualizado só via recompute; irrelevante p/ a série
    await session.commit()
    return p


async def test_cumulative_weighted_totals(session):
    """Eventos em dias diferentes → pontos reais com totais ponderados 0.965."""
    now = _now()
    p = await seed(
        session,
        times=[now - timedelta(days=5), now - timedelta(days=3), now - timedelta(days=1)],
        pps=[100.0, 50.0, 30.0],
    )
    history = await build_pp_history(session, p, days=DEFAULT_DAYS)

    real = [pt for pt in history["points"] if not pt["estimated"]]
    # 3 eventos; o ponto 0 do início da janela é estimado (sem scores antigos).
    # Sem ponto "Agora": o valor atual já está no perfil do jogador.
    assert len(real) == 3
    totals = [pt["pp_total"] for pt in real]
    assert totals[0] == pytest.approx(100.0)
    assert totals[1] == pytest.approx(100 + 50 * 0.965)  # 148.25
    assert totals[2] == pytest.approx(100 + 50 * 0.965 + 30 * 0.965**2)
    assert all(pt["estimated"] is False for pt in real)
    # sub-componentes presentes
    assert all("pp_acc" in pt and "pp_tech" in pt and "pp_speed" in pt for pt in real)


async def test_same_day_collapses(session):
    """Dois scores no mesmo dia → um único ponto real do dia, com ambos os PPs."""
    now = _now()
    p = await seed(
        session,
        times=[now - timedelta(days=5, hours=2), now - timedelta(days=5, hours=1)],
        pps=[100.0, 80.0],
    )
    history = await build_pp_history(session, p, days=DEFAULT_DAYS)
    real = [pt for pt in history["points"] if not pt["estimated"]]
    # 1 evento do dia (sem ponto "Agora" — o PP atual está no perfil)
    assert len(real) == 1
    assert real[0]["pp_total"] == pytest.approx(100 + 80 * 0.965)


async def test_gaps_interpolated_as_estimated(session):
    """Gap > 14 dias entre eventos → amostras estimadas interpoladas no meio."""
    now = _now()
    p = await seed(
        session,
        times=[now - timedelta(days=100), now - timedelta(days=20)],
        pps=[100.0, 200.0],
    )
    history = await build_pp_history(session, p, days=DEFAULT_DAYS)
    estimated = [pt for pt in history["points"] if pt["estimated"]]
    assert estimated, "esperava amostras estimadas no gap"

    # amostras estimadas ficam entre 0 (borda) e o 2º total (200 + 100×0.965);
    # pelo menos uma delas cruza o gap entre os dois eventos reais (>100)
    second_total = 200 + 100 * 0.965
    assert all(0.0 <= pt["pp_total"] <= second_total for pt in estimated)
    assert any(pt["pp_total"] > 100.0 for pt in estimated)

    # pontos reais seguem sem a flag (2º evento: 200 é o maior → 200 + 100×0.965)
    real = [pt for pt in history["points"] if not pt["estimated"]]
    assert [pt["pp_total"] for pt in real[:2]] == pytest.approx(
        [100.0, 200 + 100 * 0.965]
    )


async def test_pre_window_scores_are_initial_state(session):
    """Score anterior à janela vira o total real no início da janela (não estimado)."""
    now = _now()
    p = await seed(
        session,
        times=[now - timedelta(days=200), now - timedelta(days=10)],
        pps=[150.0, 50.0],
    )
    history = await build_pp_history(session, p, days=DEFAULT_DAYS)  # janela de 180d
    real = [pt for pt in history["points"] if not pt["estimated"]]
    # 1º ponto real no início da janela com o score antigo já contando
    assert real[0]["pp_total"] == pytest.approx(150.0)
    assert real[1]["pp_total"] == pytest.approx(150 + 50 * 0.965)


async def test_days_clamp(session):
    """days é limitado a 7..180 (mín/máx)."""
    now = _now()
    p = await seed(session, times=[now - timedelta(days=1)], pps=[100.0])
    assert (await build_pp_history(session, p, days=5))["days"] == MIN_DAYS
    assert (await build_pp_history(session, p, days=999))["days"] == MAX_DAYS
    assert (await build_pp_history(session, p, days=30))["days"] == 30


async def test_no_scores_returns_empty(session):
    p = Player(ss_id="novo", name="Novo")
    session.add(p)
    await session.commit()
    history = await build_pp_history(session, p, days=DEFAULT_DAYS)
    assert history["points"] == []
    assert history["current_pp_total"] is None


async def test_estimate_gap_constant_sane(session):
    """Constante de gap: limites válidos usados pela UI."""
    assert ESTIMATE_GAP_DAYS > 0 and MIN_DAYS <= MAX_DAYS
