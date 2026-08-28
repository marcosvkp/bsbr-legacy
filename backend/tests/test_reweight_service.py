"""Testes do serviço de reweight (persistência, auto-aplicação, auditoria)."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import Difficulty, Map, Player, RatingHistory, ReweightSuggestion, SuggestionStatus
from app.services.reweight.service import (
    apply_suggestion,
    collect_suggestions,
    reject_suggestion,
)


@pytest.fixture(autouse=True)
def _no_ml_network(monkeypatch):
    """Os testes não devem baixar beatmaps do BeatSaver (rede lenta/frágil):
    o ML fica indisponível e a análise cai para a performance (fallback)."""
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


async def make_difficulty(session, *, total=5.0, acc=1.0, tech=3.0, speed=1.0) -> Difficulty:
    m = Map(hash=f"h{total}-{acc}-{tech}", name="Mapa", status="ranked")
    session.add(m)
    await session.flush()
    d = Difficulty(
        map_id=m.id,
        characteristic="Standard",
        name="ExpertPlus",
        total_stars=total,
        acc_stars=acc,
        tech_stars=tech,
        speed_stars=speed,
    )
    session.add(d)
    await session.commit()
    return d


def score_row(acc: float, ss_pp: float = 5000.0, rank: int = 1):
    return {
        "acc": acc,
        "base_score": int(acc * 1_000_000),
        "full_combo": True,
        "player_pp": ss_pp,
        "rank": rank,
    }


async def seed_scores(session, difficulty_id: int, accs: list[float]):
    from app.models import Score

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


async def test_auto_applies_high_confidence_small_delta(session):
    d = await make_difficulty(session)
    # esperada p/ 5★ é 90.5%; mediana 91% → delta ≈ -0.13★, confiança alta
    await seed_scores(session, d.id, [0.91] * 120)

    stats = await collect_suggestions(session, auto_apply=True)
    assert stats["evaluated"] == 1
    assert stats["auto_applied"] == 1

    await session.refresh(d)
    assert d.total_stars == pytest.approx(4.87)  # 5.0 - 0.13
    # sub-stars reescalados proporcionalmente (fator 4.87/5.0)
    assert d.tech_stars == pytest.approx(round(3.0 * (4.87 / 5.0), 2))

    history = (await session.scalars(select(RatingHistory))).all()
    assert len(history) == 1
    assert history[0].applied_by == "system"
    assert history[0].total_stars_before == 5.0 and history[0].total_stars_after == pytest.approx(4.87)

    sug = (await session.scalars(select(ReweightSuggestion))).one()
    assert sug.status == SuggestionStatus.APPLIED


async def test_low_confidence_goes_to_pending_queue(session):
    d = await make_difficulty(session)
    await seed_scores(session, d.id, [0.93] * 15)  # n=15 → confiança baixa

    stats = await collect_suggestions(session, auto_apply=True)
    assert stats["auto_applied"] == 0 and stats["pending"] == 1

    sug = (await session.scalars(select(ReweightSuggestion))).one()
    assert sug.status == SuggestionStatus.PENDING
    assert sug.confidence == "low"

    # staff aplica manualmente
    applied = await apply_suggestion(session, sug.id, reviewer="staff123")
    assert applied.status == SuggestionStatus.APPLIED and applied.reviewed_by == "staff123"
    await session.refresh(d)
    assert d.total_stars < 5.0  # nerf aplicado
    hist = (await session.scalars(select(RatingHistory))).all()
    assert len(hist) == 1 and hist[0].applied_by == "staff123"


async def test_reject_keeps_rating_untouched(session):
    d = await make_difficulty(session)
    await seed_scores(session, d.id, [0.70] * 60)  # buff grande → pendente
    stats = await collect_suggestions(session)
    assert stats["pending"] == 1
    sug = (await session.scalars(select(ReweightSuggestion))).one()
    await reject_suggestion(session, sug.id, reviewer="staff9")
    await session.refresh(d)
    assert d.total_stars == 5.0
    assert (await session.scalars(select(RatingHistory))).first() is None


async def test_dedup_pending_per_difficulty(session):
    d = await make_difficulty(session)
    await seed_scores(session, d.id, [0.93] * 15)
    await collect_suggestions(session)
    # segunda rodada sem novos scores não duplica a pendente
    await collect_suggestions(session)
    sugs = (await session.scalars(select(ReweightSuggestion))).all()
    assert len(sugs) == 1


async def test_preview_suggestions_reports_impact_without_persisting(session):
    """preview_suggestions analisa em memória e devolve impacto no ranking."""
    from app.services.reweight.service import preview_suggestions

    d = await make_difficulty(session)
    # 5★ → esperada 90.5%; mediana 91% → delta ≈ -0.13★, confiança alta
    await seed_scores(session, d.id, [0.91] * 120)
    # o preview simula sobre o Score.pp (preenchido pelo sync em produção)
    from app.models import Score

    for s in (await session.scalars(select(Score))).all():
        s.pp = 100.0
        s.pp_acc = 20.0
        s.pp_tech = 60.0
        s.pp_speed = 20.0
    await session.commit()

    data = await preview_suggestions(session)
    assert len(data["difficulties"]) == 1
    item = data["difficulties"][0]
    assert item["map_name"] == "Mapa"
    assert item["difficulty"] == "ExpertPlus"
    assert item["current_stars"] == 5.0
    assert item["suggested_stars"] < 5.0
    assert item["delta_stars"] < 0
    assert item["confidence"] == "high"
    assert item["sample_size"] == 120
    assert item["auto_appliable"] is True

    assert len(data["ranking"]) >= 1
    row = data["ranking"][0]
    assert row["name"] == "Jogador"
    assert row["rank_before"] == 1 and row["rank_after"] == 1
    assert row["pp_after"] < row["pp_before"]

    # nada persistido (sem sugestões nem mudança de stars)
    from app.models import ReweightSuggestion

    assert (await session.scalars(select(ReweightSuggestion))).all() == []
    await session.refresh(d)
    assert d.total_stars == 5.0


async def test_analyze_with_ml_combines_ml_and_performance(session, monkeypatch):
    """O delta final é a média da predição do ML e da performance observada."""
    import app.services.reweight.service as service

    async def _fake_ml(map_source):
        # o ML "acha" que a dificuldade vale 6.0★ (mapa está com 5.0★)
        return {"ExpertPlus": 6.0}

    monkeypatch.setattr(service, "_ml_stars_by_difficulty", _fake_ml)

    # 5★ com acc 91% (esperado 90.5%) → delta_perf ≈ -0.13★
    d = await make_difficulty(session, total=5.0, acc=2.5, tech=1.5, speed=1.0)
    await seed_scores(session, d.id, [0.91] * 60)
    from app.models import Map as MapModel
    from app.models import Score

    for s in (await session.scalars(select(Score))).all():
        s.pp = 100.0
    await session.commit()
    m = (await session.scalars(select(MapModel))).one()

    scores = await service._difficulty_scores(session, d.id)
    result = await service.analyze_difficulty_with_ml(d, m, scores)
    # delta_ml = +1.0 (ML 6.0 - atual 5.0) e delta_perf ≈ -0.13 → média ≈ +0.43
    assert result.confidence == "medium"  # n=60
    assert 0.3 < result.delta_stars < 0.6
    assert 5.3 < result.suggested_stars < 5.6
    assert "ML 6.00\u2605" in result.reason
    assert result.direction == "increase"
