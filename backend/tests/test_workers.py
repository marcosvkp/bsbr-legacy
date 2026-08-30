"""Testes das tasks do Celery (workers)."""

import asyncio

from sqlalchemy import text


def test_sync_br_daily_runs_twice_in_separate_loops():
    """Regressão do 'attached to a different loop' (asyncpg no celery).

    A task roda `asyncio.run()` por execução (loop novo). O dispose_engine()
    no início recria o pool no loop atual, permitindo execuções sucessivas
    sem reusar conexões de um loop já fechado.
    """
    from app.core.db import SessionLocal, dispose_engine

    async def run_once(n: int) -> int:
        await dispose_engine()
        async with SessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar()

    first = asyncio.run(run_once(1))
    second = asyncio.run(run_once(2))  # loop novo, como asyncio.run na task
    assert first == 1
    assert second == 1
