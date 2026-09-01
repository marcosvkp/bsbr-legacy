"""Testes da amostra global + remap por faixa de estrelas (Plan Algoryth §3).

Cobre: suplemento global fraco com doadores, global suficiente, remap puro
sem amostra própria, coerência de acc (descartar doador mal calibrado),
remap insuficiente → sem sugestão, auto-apply de pool 100+ e preview com
fonte. Scores globais/doadores nunca são gravados em scores/players.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app.integrations.scoresaber import LeaderboardScoresResult
from app.models import (
    Difficulty,
    Map,
    MapStatus,
    Player,
    RatingHistory,
    ReweightSuggestion,
    Score,
    SuggestionStatus,
)
from app.services.reweight.service import collect_suggestions, preview_suggestions


@pytest.fixture(autouse=True)
def _no_ml_network(monkeypatch):
    import app.services.reweight.service as service

    async def _no_ml(map_source):
        return None

    monkeypatch.setattr(service, "_ml_stars_by_difficulty", _no_ml)


@pytest.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/global.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


def raw_score(acc: float, rank: int) -> dict:
    return {
        "baseScore": int(acc * 900_000),
        "modifiedScore": int(acc * 900_000),
        "rank": rank,
        "fullCombo": True,
        "leaderboardPlayerInfo": {"id": f"76561198{rank:08d}", "name": f"P{rank}"},
    }


def cand(lb_id: int, *, hash_: str = "a" * 40, total_scores: int = 100) -> dict:
    return {
        "id": str(lb_id),
        "map": {"hash": hash_},
        "maxScore": 900_000,
        "totalScores": total_scores,
    }


class FakeScoreSaber:
    """Cliente ScoreSaber falso: leaderboards globais + busca por faixa."""

    def __init__(self):
        self.lb_payloads: dict[str, list[dict]] = {}
        self.candidates: dict[tuple[float, float], list[dict]] = {}
        self.calls: list[tuple] = []

    async def close(self):
        pass

    async def leaderboard_info_by_id(self, leaderboard_id):
        self.calls.append(("info", str(leaderboard_id)))
        return {"maxScore": 900_000}

    async def leaderboard_scores_by_id_with_status(self, leaderboard_id, *, country=None, max_pages=None):
        self.calls.append(("scores", str(leaderboard_id), country, max_pages))
        payload = self.lb_payloads.get(str(leaderboard_id), [])
        return LeaderboardScoresResult(
            scores=payload, transport_ok=True, exhausted=True, pages_fetched=1
        )

    async def ranked_leaderboards_by_star_band(self, min_stars, max_stars, *, limit=50, page=1):
        self.calls.append(("band", min_stars, max_stars))
        return self.candidates.get((min_stars, max_stars), [])


async def make_ranked(session, *, stars: float = 5.0, ss_lb: str = "999") -> Difficulty:
    m = Map(hash="h" * 40, name="Mapa Alvo", mapper="MapperX", status=MapStatus.RANKED)
    session.add(m)
    await session.flush()
    d = Difficulty(
        map_id=m.id,
        characteristic="Standard",
        name="ExpertPlus",
        total_stars=stars,
        is_ranked=True,
        ss_leaderboard_id=ss_lb,
        max_score=900_000,
    )
    session.add(d)
    await session.commit()
    return d


async def seed_local(session, difficulty_id: int, accs: list[float]) -> None:
    for i, acc in enumerate(accs):
        p = Player(ss_id=f"loc{i}", name=f"Local{i}", pp_total=2000)
        session.add(p)
        await session.flush()
        session.add(
            Score(
                player_id=p.id,
                difficulty_id=difficulty_id,
                score=int(acc * 1_000_000),
                acc=acc,
                ss_player_pp=2000.0,
                full_combo=True,
                leaderboard_rank=i + 1,
                time_set=datetime(2026, 8, 20, 12, i % 60),
            )
        )
    await session.commit()


def add_global(fake: FakeScoreSaber, lb_id: str, acc: float, n: int) -> None:
    fake.lb_payloads[lb_id] = [raw_score(acc, rank=i + 1) for i in range(n)]


def add_donors(fake: FakeScoreSaber, n_donors: int, acc: float, *, band=(4.5, 5.5)) -> None:
    for i in range(n_donors):
        c = cand(100 + i)
        fake.candidates.setdefault(band, []).append(c)
        fake.lb_payloads[c["id"]] = [raw_score(acc, rank=r + 1) for r in range(12)]


async def _first_suggestion(session) -> ReweightSuggestion:
    return (
        await session.scalars(
            select(ReweightSuggestion).where(ReweightSuggestion.status == SuggestionStatus.PENDING)
        )
    ).first()


async def _score_count(session) -> int:
    return (await session.execute(select(func.count(Score.id)))).scalar()


# ── Global suficiente ────────────────────────────────────────────────────────


async def test_global_sufficient_uses_scoresaber_global(session):
    d = await make_ranked(session)
    fake = FakeScoreSaber()
    add_global(fake, "999", acc=0.90, n=60)  # >= REMAP_TARGET=50

    stats = await collect_suggestions(session, use_global=True, score_client=fake)

    sug = await _first_suggestion(session)
    assert sug is not None
    assert sug.sample_source == "scoresaber_global"
    assert sug.sample_size == 60
    assert stats["global_difficulties_used"] == 1
    assert stats["br_fallbacks"] == 0
    assert ("band", 4.5, 5.5) not in fake.calls  # não precisou de remap
    assert await _score_count(session) == 0  # nada global persistido


# ── Suplemento global fraco → remap ──────────────────────────────────────────


async def test_global_weak_supplemented_by_remap(session):
    d = await make_ranked(session)
    fake = FakeScoreSaber()
    add_global(fake, "999", acc=0.90, n=20)  # 6 <= 20 < 50
    add_donors(fake, 5, acc=0.90)

    stats = await collect_suggestions(session, use_global=True, score_client=fake)

    sug = await _first_suggestion(session)
    assert sug is not None
    assert sug.sample_source == "remap"
    assert sug.sample_size == 20 + 5 * 12  # 80
    assert stats["remap_difficulties_used"] == 1
    assert stats["global_scores_fetched"] == 1
    assert stats["remap_scores_fetched"] == 5
    assert stats["remap_candidates_found"] == 5
    assert stats["remap_donors_used"] == 5
    assert await _score_count(session) == 0


# ── Remap puro (sem amostra própria) ─────────────────────────────────────────


async def test_pure_remap_when_no_local_or_global_sample(session):
    d = await make_ranked(session)
    fake = FakeScoreSaber()
    # global vazio, local com 3 scores (< MIN_SCORES)
    await seed_local(session, d.id, [0.90] * 3)
    add_donors(fake, 4, acc=0.90)

    stats = await collect_suggestions(session, use_global=True, score_client=fake)

    sug = await _first_suggestion(session)
    assert sug is not None
    assert sug.sample_source == "remap"
    assert sug.sample_size == 3 + 4 * 12  # 51 >= MIN_SCORES
    assert stats["remap_difficulties_used"] == 1
    assert await _score_count(session) == 3  # só os locais originais


# ── Coerência de acc ─────────────────────────────────────────────────────────


async def test_remap_drops_outlier_donor(session):
    d = await make_ranked(session)
    fake = FakeScoreSaber()
    add_global(fake, "999", acc=0.90, n=20)
    # 3 doadores coerentes (0.90) + 1 outlier (0.60) → descartado pelo σ
    add_donors(fake, 3, acc=0.90)
    outlier = cand(500, hash_="b" * 40)
    fake.candidates[(4.5, 5.5)].append(outlier)
    fake.lb_payloads[outlier["id"]] = [raw_score(0.60, rank=r + 1) for r in range(12)]

    await collect_suggestions(session, use_global=True, score_client=fake)

    sug = await _first_suggestion(session)
    assert sug is not None
    assert sug.sample_size == 20 + 3 * 12  # outlier fora do pool


async def test_remap_insufficient_donors_means_no_suggestion(session):
    d = await make_ranked(session)
    fake = FakeScoreSaber()
    # global vazio + local fraco + apenas 2 doadores (< REMAP_MIN_DONORS)
    await seed_local(session, d.id, [0.90] * 3)
    add_donors(fake, 2, acc=0.90)

    stats = await collect_suggestions(session, use_global=True, score_client=fake)

    assert stats["evaluated"] == 0
    assert stats["remap_difficulties_used"] == 0
    assert (await session.scalars(select(ReweightSuggestion))).first() is None


# ── Auto-apply de pool remap 100+ ────────────────────────────────────────────


async def test_remap_pool_over_100_auto_applies(session):
    d = await make_ranked(session)
    fake = FakeScoreSaber()
    add_global(fake, "999", acc=0.90, n=20)
    add_donors(fake, 8, acc=0.90)  # 20 + 96 = 116 >= 100 → high

    stats = await collect_suggestions(session, auto_apply=True, use_global=True, score_client=fake)

    sug = (await session.scalars(select(ReweightSuggestion))).first()
    assert sug is not None
    assert sug.sample_source == "remap"
    assert sug.status == SuggestionStatus.APPLIED
    assert stats["auto_applied"] == 1
    # RatingHistory gravado (aplicação), scores globais NÃO
    assert (await session.scalars(select(RatingHistory))).first() is not None
    assert await _score_count(session) == 0


# ── Preview com fonte ────────────────────────────────────────────────────────


async def test_preview_reports_sample_source(session):
    d = await make_ranked(session)
    fake = FakeScoreSaber()
    add_global(fake, "999", acc=0.90, n=60)

    data = await preview_suggestions(session, use_global=True, score_client=fake)

    assert len(data["difficulties"]) == 1
    assert data["difficulties"][0]["sample_source"] == "scoresaber_global"
    assert data["difficulties"][0]["sample_size"] == 60
