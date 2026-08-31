"""Testes das tasks do Celery (workers)."""

import asyncio

from sqlalchemy import text


def test_sync_br_daily_runs_twice_in_separate_loops():
    """Regressão do 'attached to a different loop' (asyncpg no celery).

    A task roda `asyncio.run()` por execução (loop novo). O engine global
    criado na importação carrega um pool asyncpg de um loop já fechado — a 2ª
    execução quebra. O `task_session_factory()` cria o engine DENTRO do loop
    de cada execução, isolando o pool.
    """
    from app.core.db import task_session_factory

    async def run_once(n: int) -> int:
        SessionLocal, close_db = await task_session_factory()
        try:
            async with SessionLocal() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar()
        finally:
            await close_db()

    first = asyncio.run(run_once(1))
    second = asyncio.run(run_once(2))  # loop novo, como asyncio.run na task
    assert first == 1
    assert second == 1


def test_limiter_reads_cache_redis_dynamically():
    """Regressão do 'Event loop is closed' no rate-limiter.

    O SlidingWindowLimiter capturava cache._redis no __init__ — cliente de um
    loop já fechado nas tasks celery. Agora lê dinamicamente: quando a task
    recria cache._redis (task_redis_client), o limiter passa a usar o novo.
    """
    from app.core.cache import cache
    from app.core.ratelimit import SlidingWindowLimiter

    limiter = SlidingWindowLimiter("test", 10, 60)
    assert limiter._redis is cache._redis

    fake = object()
    cache._redis = fake
    assert limiter._redis is fake  # reflete a troca feita pela task

    cache._redis = None
    assert limiter._redis is None


def test_weekly_batch_marks_failed_on_error(tmp_path, monkeypatch):
    """Regressão: erro no meio do batch deve gravar finished_at.

    Sem try/finally, uma falha no pipeline deixava o batch 'em execução'
    para sempre (finished_at nunca gravado).
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/wb.db")
    import app.core.db as dbmod
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/wb.db")
    dbmod.engine = engine
    dbmod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # Importa os models para o Base.metadata conhecer as tabelas antes do create_all.
    from app.models import Batch  # noqa: F401
    from app.core.db import Base

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_setup())

    # O sync (primeira etapa do pipeline) falha.
    import app.services.sync as syncmod

    async def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(syncmod, "sync_all_ranked_difficulties", _boom)

    import pytest

    from app.workers.tasks import run_weekly_batch

    with pytest.raises(RuntimeError):
        asyncio.run(run_weekly_batch())

    from app.models import Batch

    async def _check() -> None:
        async with dbmod.SessionLocal() as s:
            batch = (await s.scalars(select(Batch))).first()
            assert batch is not None
            assert batch.finished_at is not None
            assert batch.stats == {"failed": True}

    asyncio.run(_check())
    asyncio.run(engine.dispose())


def test_weekly_batch_reports_manual_and_auto_applies(tmp_path, monkeypatch):
    """Regressão: reweight aplicado manualmente (batch_id NULL) nunca virava
    mensagem no Discord — o batch só reportava os auto-aplicados do próprio
    batch. Agora o batch varre as manuais pendentes para o batch atual e
    reporta tudo numa mensagem só.
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/wb4.db")
    import app.core.db as dbmod
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/wb4.db")
    dbmod.engine = engine
    dbmod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    from app import models  # noqa: F401
    from app.core.db import Base
    from app.models import Difficulty, Map, MapStatus, RatingHistory

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with dbmod.SessionLocal() as s:
            m = Map(hash="d" * 40, name="Mapa Manual", mapper="MapperY", status=MapStatus.RANKED)
            s.add(m)
            await s.flush()
            d = Difficulty(
                map_id=m.id,
                characteristic="Standard",
                name="ExpertPlus",
                total_stars=6.0,
                is_ranked=True,
            )
            s.add(d)
            await s.flush()
            # Aplicação manual prévia: batch_id NULL (não reportada ainda)
            s.add(
                RatingHistory(
                    difficulty_id=d.id,
                    total_stars_before=6.0,
                    total_stars_after=5.0,
                    reason="aplicação manual",
                    applied_by="staff",
                    batch_id=None,
                )
            )
            await s.commit()
            return d.id

    manual_diff_id = asyncio.run(_setup())

    import app.services.playlist as playlistmod
    import app.services.ranking as rankingmod
    import app.services.reweight.service as reweightmod
    import app.services.sync as syncmod

    async def _no_sync(*args, **kwargs):
        return []

    async def _no_collect(session, *, batch_id=None):
        # Simula o auto-apply do batch: RatingHistory ligada ao batch atual
        session.add(
            RatingHistory(
                difficulty_id=manual_diff_id,
                total_stars_before=5.0,
                total_stars_after=4.5,
                reason="auto-apply",
                batch_id=batch_id,
            )
        )
        return {"evaluated": 1, "pending": 0, "auto_applied": 1}

    class _Ranking:
        players_updated = 0

    async def _no_ranking(*args, **kwargs):
        return _Ranking()

    async def _no_snapshot(*args, **kwargs):
        return 0

    async def _no_playlist(*args, **kwargs):
        return None

    monkeypatch.setattr(syncmod, "sync_all_ranked_difficulties", _no_sync)
    monkeypatch.setattr(reweightmod, "collect_suggestions", _no_collect)
    monkeypatch.setattr(rankingmod, "recompute_all_rankings", _no_ranking)
    monkeypatch.setattr(rankingmod, "write_weekly_snapshot", _no_snapshot)
    monkeypatch.setattr(playlistmod, "generate_bsbr_playlist", _no_playlist)

    sent = {}

    async def _fake_send(db, rows, title=None):
        sent["rows"] = rows
        sent["title"] = title
        return 1

    import app.integrations.discord as discordmod

    monkeypatch.setattr(discordmod, "send_reweight_report", _fake_send)

    from app.workers.tasks import run_weekly_batch

    stats = asyncio.run(run_weekly_batch())

    # Uma mensagem só, com a manual + a auto
    assert sent.get("rows") is not None, "batch com aplicações deve notificar"
    assert len(sent["rows"]) == 2
    names = {r["map_name"] for r in sent["rows"]}
    assert names == {"Mapa Manual"}
    assert stats["ratings_changed"] == 2, stats

    # A manual foi varrida para o batch (auditoria) → não re-reporta depois
    from sqlalchemy import select

    async def _check_swept() -> None:
        from app.models import Batch

        async with dbmod.SessionLocal() as s:
            batch = (await s.scalars(select(Batch))).first()
            h = (await s.scalars(select(RatingHistory).where(RatingHistory.batch_id.is_(None)))).all()
            assert batch is not None
            assert h == [], "nenhuma manual deve sobrar sem batch"

    asyncio.run(_check_swept())
    asyncio.run(engine.dispose())
