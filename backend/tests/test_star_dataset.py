"""Testes do dataset de referência (star_reference + curva empírica)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import StarReference
from app.services.reweight import curve, expected_median_acc


@pytest.fixture(autouse=True)
def _clean_curve():
    curve.reset_curve()
    yield
    curve.reset_curve()


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/star.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


def test_band_for_rounds_to_half_star():
    assert curve.band_for(5.3) == 5.5
    assert curve.band_for(5.2) == 5.0
    assert curve.band_for(4.75) == 5.0


def test_expected_median_acc_falls_back_to_formula_without_dataset():
    assert expected_median_acc(5) == pytest.approx(0.905)
    assert expected_median_acc(14) == pytest.approx(0.78)  # piso


async def test_load_curve_aggregates_bands(session):
    session.add_all(
        [
            StarReference(source="scoresaber", leaderboard_id="1", stars=5.3, median_top_acc=0.91, sample_n=10),
            StarReference(source="scoresaber", leaderboard_id="2", stars=5.4, median_top_acc=0.93, sample_n=12),
            StarReference(source="scoresaber", leaderboard_id="3", stars=5.6, median_top_acc=0.89, sample_n=8),
            # amostra esparsa (sample_n < MIN_SAMPLES_PER_BAND) → banda ignorada
            StarReference(source="scoresaber", leaderboard_id="4", stars=7.8, median_top_acc=0.80, sample_n=2),
            StarReference(source="beatleader", leaderboard_id="5", stars=15.2, median_top_acc=0.72, sample_n=20),
        ]
    )
    await session.commit()

    await curve.load_curve(session)

    # banda 5.5 (5.3/5.4/5.6): mediana de [0.91, 0.93, 0.89] = 0.91
    assert curve.empirical_expected_acc(5.3) == pytest.approx(0.91)
    # banda esparsa → None (fallback fórmula no expected_median_acc)
    assert curve.empirical_expected_acc(7.8) is None
    # curvas separadas por fonte
    assert curve.empirical_expected_acc(15.2, "beatleader") == pytest.approx(0.72)
    assert curve.empirical_expected_acc(15.2) is None
    # banda sem dataset → None
    assert curve.empirical_expected_acc(2.0) is None

    # expected_median_acc usa a curva carregada e cai pra fórmula onde é esparsa
    assert expected_median_acc(5.3) == pytest.approx(0.91)
    assert expected_median_acc(7.8) == pytest.approx(0.98 - 7.8 * 0.015)


async def test_load_curve_refresh(session):
    session.add(
        StarReference(source="scoresaber", leaderboard_id="1", stars=5.3, median_top_acc=0.90, sample_n=10)
    )
    await session.commit()
    await curve.load_curve(session)
    assert curve.empirical_expected_acc(5.3) == pytest.approx(0.90)

    # sem refresh não recarrega
    session.add(
        StarReference(source="scoresaber", leaderboard_id="2", stars=5.4, median_top_acc=0.95, sample_n=10)
    )
    await session.commit()
    await curve.load_curve(session)
    assert curve.empirical_expected_acc(5.3) == pytest.approx(0.90)

    # com refresh incorpora o novo (banda 5.5: mediana [0.90, 0.95] = 0.925)
    await curve.load_curve(session, refresh=True)
    assert curve.empirical_expected_acc(5.3) == pytest.approx(0.925)
