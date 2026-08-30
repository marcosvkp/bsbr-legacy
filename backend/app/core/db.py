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


async def dispose_engine() -> None:
    """Libera o pool do engine global (deve rodar DENTRO do loop da task).

    Tasks do Celery rodam `asyncio.run()` (loop novo por execução). O pool do
    asyncpg retém conexões do loop anterior e a 2ª execução quebra com
    "attached to a different loop". Chamar no início de cada task async força
    o pool a ser recriado no loop atual. O uvicorn (FastAPI) usa um loop único
    e persistente, então nunca precisa disso.
    """
    await engine.dispose()


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency FastAPI: sessão por request."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Dev helper: cria o schema sem migração. Produção usa Alembic."""
    from app import models  # noqa: F401 — importa para registrar os mappers

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
