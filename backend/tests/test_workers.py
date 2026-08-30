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
