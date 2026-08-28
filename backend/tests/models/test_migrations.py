"""Teste funcional das migrações Alembic: upgrade head + downgrade base."""

import sqlite3
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Garante que `app` é importável mesmo rodando pytest de outra raiz.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _sqlite_tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {name for (name,) in rows}

EXPECTED_TABLES = {
    "players",
    "maps",
    "difficulties",
    "scores",
    "rating_history",
    "reweight_suggestions",
    "rank_snapshots",
    "batches",
    "staff_users",
}


def test_upgrade_head_downgrade_base(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "mig.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    # env.py dá precedência a DATABASE_URL sobre o alembic.ini
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")

    tables = _sqlite_tables(db_path)
    assert EXPECTED_TABLES <= tables, f"faltando: {EXPECTED_TABLES - tables}"
    assert "alembic_version" in tables

    # Idempotência: head já aplicado não quebra
    command.upgrade(cfg, "head")

    # Migração reflete o schema dos models (sem drift)
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from app.core.db import Base
    import app.models  # noqa: F401

    engine = __import__("sqlalchemy").create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn), Base.metadata
        )
    engine.dispose()
    assert diff == [], f"drift entre models e migração: {diff}"

    command.downgrade(cfg, "base")

    assert _sqlite_tables(db_path).isdisjoint(EXPECTED_TABLES)


def test_upgrade_twice_from_base(tmp_path, monkeypatch) -> None:
    """base → head → base → head: migração reversível e repetível."""
    db_path = tmp_path / "mig2.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= _sqlite_tables(db_path)


@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_expected_table_exists_after_upgrade(tmp_path, monkeypatch, table) -> None:
    db_path = tmp_path / f"mig_{table}.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(_alembic_config(db_url), "head")
    assert table in _sqlite_tables(db_path)
