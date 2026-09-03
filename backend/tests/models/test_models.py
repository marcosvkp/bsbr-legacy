"""Testes das entidades SQLAlchemy do BSBR (Plan.md §5)."""

from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models import (
    Batch,
    BatchKind,
    Difficulty,
    Map,
    MapStatus,
    Player,
    RankSnapshot,
    RatingHistory,
    ReweightSuggestion,
    Score,
    StaffUser,
    SuggestionStatus,
)


from app.models import (
    Batch,
    BatchKind,
    Difficulty,
    Map,
    MapStatus,
    Player,
    RankSnapshot,
    RatingHistory,
    ReweightSuggestion,
    Score,
    StaffUser,
    SuggestionStatus,
)

# pytest-asyncio em modo strict exige marca explícita nos testes assíncronos.
pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture
async def engine(tmp_path):
    """Engine SQLite em arquivo temporário com o schema completo."""
    eng = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'models.db').as_posix()}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess


@pytest_asyncio.fixture
async def sample(session: AsyncSession) -> dict[str, Any]:
    """Grafo coerente: map→difficulty→score de player, suggestion, snapshot,
    batch e rating_history — tudo persistido."""
    player = Player(
        ss_id="76561198000000001",
        name="ZephyrBR",
        country="BR",
        hmd="quest",
        pp_total=5432.10,
        pp_acc=1200.0,
        pp_tech=2600.5,
        pp_speed=1631.6,
        rank=3,
    )
    map_ = Map(
        hash="a1b2c3d4e5f6a7b8c9d0",
        beatsaver_id="2a1b0",
        name="Neon Genesis",
        song_author="Camellia",
        mapper="Kry.exe",
        bpm=200.0,
        tags=["tech", "speed"],
        status=MapStatus.RANKED,
        submitted_by="76561198000000001",
    )
    difficulty = Difficulty(
        map=map_,
        characteristic="Standard",
        name="Expert+",
        njs=20.0,
        max_score=1_086_900,
        max_pp=650.25,
        total_stars=9.35,
        acc_stars=6.1,
        tech_stars=9.4,
        speed_stars=7.8,
        features={"tech_density": 0.72, "peak_nps": 14.2},
        style_tags=["tech", "speed"],
        model_version="v0.3",
    )
    score = Score(
        player=player,
        difficulty=difficulty,
        score=985_400,
        acc=0.9063,
        modifiers="",
        full_combo=True,
        pp=520.75,
        pp_acc=110.0,
        pp_tech=250.0,
        pp_speed=160.75,
        leaderboard_rank=1,
        time_set=datetime(2026, 8, 15, 12, 30, tzinfo=UTC),
    )
    batch = Batch(kind=BatchKind.WEEKLY)
    rating = RatingHistory(
        difficulty=difficulty,
        total_stars_before=9.55,
        total_stars_after=9.35,
        tech_stars_before=9.6,
        tech_stars_after=9.4,
        reason="reweight semanal: observed_acc acima do esperado",
        batch=batch,
        applied_by="111222333444555666",
    )
    suggestion = ReweightSuggestion(
        difficulty=difficulty,
        observed_acc=0.94,
        expected_acc=0.91,
        sample_size=420,
        delta_stars=-0.2,
        confidence=0.87,
    )
    snapshot = RankSnapshot(
        week="2026-W33",
        player=player,
        rank=3,
        pp_total=5432.10,
        pp_acc=1200.0,
        pp_tech=2600.5,
        pp_speed=1631.6,
    )
    staff = StaffUser(ss_id="76561198000000002", role="admin")

    session.add_all([player, map_, difficulty, score, batch, rating, suggestion, snapshot, staff])
    await session.commit()

    return {
        "player": player,
        "map": map_,
        "difficulty": difficulty,
        "score": score,
        "batch": batch,
        "rating": rating,
        "suggestion": suggestion,
        "snapshot": snapshot,
        "staff": staff,
    }


async def test_roundtrip(session: AsyncSession, sample: dict[str, Any]) -> None:
    """Releitura do grafo persistido: colunas, JSONs e relacionamentos."""
    result = await session.execute(select(Player).where(Player.ss_id == "76561198000000001"))
    player = result.scalar_one()
    assert player.name == "ZephyrBR"
    assert player.country == "BR"
    assert (player.pp_total, player.pp_tech) == (5432.10, 2600.5)

    assert len(player.scores) == 1
    score = player.scores[0]
    assert score.acc == pytest.approx(0.9063)
    assert score.full_combo is True
    assert score.difficulty.total_stars == pytest.approx(9.35)
    assert score.difficulty.map.hash == "a1b2c3d4e5f6a7b8c9d0"

    # back_populates nos dois sentidos
    diff = score.difficulty
    assert diff.map.difficulties[0].id == diff.id
    assert diff.scores[0].player_id == player.id

    # JSONB-like roundtrip
    assert diff.features["peak_nps"] == 14.2
    assert diff.style_tags == ["tech", "speed"]

    # rating_history ↔ batch
    rating = diff.rating_history[0]
    assert rating.batch.kind is BatchKind.WEEKLY
    assert rating.total_stars_before == pytest.approx(9.55)
    assert rating.applied_at is not None

    # suggestion pendente por padrão
    sugg = diff.reweight_suggestions[0]
    assert sugg.status is SuggestionStatus.PENDING

    # snapshot
    snap = player.rank_snapshots[0]
    assert snap.week == "2026-W33"
    assert snap.rank == 3


async def test_enum_and_timestamp_defaults(session: AsyncSession) -> None:
    """Defaults de enum persistem como valor lowercase; timestamps têm server_default."""
    map_ = Map(hash="deadbeef" * 4, name="Untitled")
    batch = Batch()
    staff = StaffUser(ss_id="76561198000000003")
    session.add_all([map_, batch, staff])
    await session.commit()

    await session.refresh(map_)
    await session.refresh(batch)
    assert map_.status is MapStatus.CANDIDATE
    assert map_.created_at is not None
    assert batch.kind is BatchKind.MANUAL
    assert batch.started_at is not None
    assert batch.finished_at is None
    assert staff.role == "staff"


async def test_unique_player_ss_id(session: AsyncSession, sample) -> None:
    session.add(Player(ss_id="76561198000000001", name="Clone"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_unique_map_hash(session: AsyncSession, sample) -> None:
    session.add(Map(hash="a1b2c3d4e5f6a7b8c9d0", name="Duplicated hash"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

async def test_unique_score_player_difficulty_time_set(session: AsyncSession, sample) -> None:
    original: Score = sample["score"]
    # Captura antes: o rollback após a violação expira os objetos da sessão.
    player_id = original.player_id
    difficulty_id = original.difficulty_id
    same_time = original.time_set
    session.add(
        Score(
            player_id=player_id,
            difficulty_id=difficulty_id,
            score=100,
            time_set=same_time,  # mesmo trio → viola uniq
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # time_set diferente → aceito
    session.add(
        Score(
            player_id=player_id,
            difficulty_id=difficulty_id,
            score=100,
            time_set=datetime(2026, 8, 16, 1, 2, 3, tzinfo=UTC),
        )
    )
    await session.commit()


async def test_unique_rank_snapshot_week_player(session: AsyncSession, sample) -> None:
    snap: RankSnapshot = sample["snapshot"]
    session.add(RankSnapshot(week=snap.week, player_id=snap.player_id))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_unique_staff_ss_id(session: AsyncSession, sample) -> None:
    session.add(StaffUser(ss_id="76561198000000002"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_cascade_delete_difficulty_removes_scores(engine, sample) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        # Delete via ORM: o cascade "all, delete-orphan" remove os filhos.
        diff = await sess.get(Difficulty, sample["difficulty"].id)
        assert diff is not None
        await sess.delete(diff)
        await sess.commit()

    async with maker() as sess:
        assert (await sess.execute(select(Score))).scalars().all() == []
        assert (await sess.execute(select(RatingHistory))).scalars().all() == []
        assert (await sess.execute(select(ReweightSuggestion))).scalars().all() == []
        # O mapa permanece; apenas a difficulty e dependentes somem.
        assert (await sess.execute(select(Map))).scalars().one().id == sample["map"].id
