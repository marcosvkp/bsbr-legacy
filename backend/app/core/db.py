import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base declarativa compartilhada por todos os models."""


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite local precisa do diretório pai existente para abrir o arquivo."""
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix):
        Path(url.removeprefix(prefix)).parent.mkdir(parents=True, exist_ok=True)


_settings = get_settings()
_ensure_sqlite_dir(_settings.database_url)

engine = create_async_engine(_settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Referência do engine original criado na importação. Os testes substituem
# `dbmod.engine`/`dbmod.SessionLocal` por um mock (sqlite temporário); o
# task_session_factory usa essa referência para detectar a substituição.
_ORIGINAL_ENGINE = engine
_ORIGINAL_SESSION_LOCAL = SessionLocal


async def dispose_engine() -> None:
    """Libera o pool do engine global (deve rodar DENTRO do loop da task).

    Tasks do Celery rodam `asyncio.run()` (loop novo por execução). O pool do
    asyncpg retém conexões do loop anterior e a 2ª execução quebra com
    "attached to a different loop". Chamar no início de cada task async força
    o pool a ser recriado no loop atual. O uvicorn (FastAPI) usa um loop único
    e persistente, então nunca precisa disso.
    """
    await engine.dispose()


async def task_session_factory():
    """Retorna (sessionmaker, close) para a task atual — engine isolado por loop.

    Uso em tasks do Celery que rodam `asyncio.run()` (loop novo por execução).
    Um engine global criado na importação (processo pai do fork) carrega um
    pool asyncpg de um loop que já foi fechado — a 2ª execução quebra com
    "attached to a different loop" mesmo com dispose_engine(). Criar o engine
    dentro do loop da task isola o pool por execução e elimina o problema de
    raiz. Não usar em código FastAPI (uvicorn tem loop único).

    Nos testes, o engine global é substituído (mock p/ sqlite temporário);
    detectamos isso comparando a URL e reutilizamos o sessionmaker global
    quando o engine já foi mockado — assim o `admin/batch/run` (eager, mesmo
    processo) enxerga o schema/seed do teste.
    """
    import app.core.db as dbmod

    if dbmod.engine is not _ORIGINAL_ENGINE:
        # engine global foi substituído (testes) — usa o sessionmaker mockado
        async def _noop_close() -> None:
            return None

        return dbmod.SessionLocal, _noop_close

    settings = get_settings()
    _ensure_sqlite_dir(settings.database_url)
    task_engine = create_async_engine(settings.database_url, echo=False, future=True)
    task_sessionmaker = async_sessionmaker(task_engine, expire_on_commit=False)

    async def close() -> None:
        await task_engine.dispose()

    return task_sessionmaker, close


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency FastAPI: sessão por request."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Dev helper: cria o schema sem migração. Produção usa Alembic."""
    from app import models  # noqa: F401 — importa para registrar os mappers

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
