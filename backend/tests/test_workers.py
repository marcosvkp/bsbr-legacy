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
