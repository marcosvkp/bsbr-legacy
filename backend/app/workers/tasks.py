"""Tarefas Celery — incluindo a pipeline do batch semanal (Plan.md §3.4)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.orm import joinedload


@shared_task(name="ping")
def ping() -> str:
    """Sanity check da fila/workers."""
    return "pong"


async def run_weekly_batch() -> dict:
    from app.core.cache import cache
    from app.core.db import task_session_factory  # engine isolado por loop (tasks celery)

    # O cliente Redis é criado no loop desta execução; o cache troca clientes
    # quando uma nova execução de asyncio.run usa outro loop.
    await cache._ensure_redis()  # noqa: SLF001

    SessionLocal, close_db = await task_session_factory()
    from app.integrations.discord import history_rows, send_reweight_report
    from app.models import Batch, BatchKind, Difficulty, RatingHistory
    from app.services.playlist import generate_bsbr_playlist
    from app.services.ranking import recompute_all_rankings, write_weekly_snapshot
    from app.services.reweight.service import collect_suggestions
    from app.services.sync import sync_all_ranked_difficulties

    async with SessionLocal() as session:
        batch = Batch(kind=BatchKind.WEEKLY)
        session.add(batch)
        await session.commit()
        batch_id = batch.id

        try:
            sync_stats = await sync_all_ranked_difficulties(session)
            reweight_stats = await collect_suggestions(session, batch_id=batch.id)
            ranking = await recompute_all_rankings(session)
            snapshot_count = await write_weekly_snapshot(session)

            # Reweights manuais (apply no admin) nascem com batch_id NULL.
            # O relatório sai aqui, no batch: varre as aplicações manuais
            # ainda não reportadas para este batch e reporta tudo junto
            # (manuais + auto do batch) numa mensagem só.
            manual = (
                (
                    await session.scalars(
                        select(RatingHistory).where(
                            RatingHistory.batch_id.is_(None),
                            RatingHistory.total_stars_before.is_not(None),
                        )
                    )
                )
                .all()
            )
            for h in manual:
                h.batch_id = batch.id

            changed = (
                (
                    await session.scalars(
                        select(RatingHistory)
                        .options(
                            joinedload(RatingHistory.difficulty).joinedload(Difficulty.map)
                        )
                        .where(RatingHistory.batch_id == batch.id)
                    )
                )
                .all()
            )
            playlist = await generate_bsbr_playlist(session)

            batch.finished_at = datetime.now(timezone.utc)
            batch.stats = {
                "sync_fetched": sum(s.fetched for s in sync_stats),
                "sync_inserted": sum(s.inserted for s in sync_stats),
                "reweight_evaluated": reweight_stats["evaluated"],
                "reweight_auto_applied": reweight_stats["auto_applied"],
                "reweight_pending": reweight_stats["pending"],
                "players_updated": ranking.players_updated,
                "snapshot_players": snapshot_count,
                "ratings_changed": len(changed),
            }
            await session.commit()

            # Notifica os webhooks (somente REWEIGHT de mapas; o sync/batch
            # não vai para esse endpoint). Múltiplos URLs via webhook_configs.
            if changed:
                rows = history_rows(changed)
                from datetime import datetime as _dt, timezone as _tz

                today = _dt.now(_tz.utc)
                title = f"Reweight de mapas — {today:%d/%m/%Y}"
                await send_reweight_report(session, rows, title=title)
        except Exception:
            # Sem try/finally, um erro no meio deixaria o batch 'em execução'
            # para sempre (finished_at nunca gravado). Marca como encerrado
            # com falha e repassa a exceção ao celery.
            async with SessionLocal() as fail_session:
                stale = await fail_session.get(Batch, batch_id)
                if stale is not None:
                    stale.finished_at = datetime.now(timezone.utc)
                    stale.stats = {"failed": True}
                    await fail_session.commit()
            raise
        stats = dict(batch.stats)

    await close_db()
    return stats


@shared_task(name="batch.weekly")
def weekly_batch() -> dict:
    return asyncio.run(run_weekly_batch())


@shared_task(name="sync.br_daily")
def sync_br_daily() -> dict:
    """Re-sync dos leaderboards rankeados BR (complemento do scorefeed ao vivo).

    Roda 2x/dia (06:15 e 18:15 UTC) pelo beat; também atualiza o ranking
    após a ingestão para o site refletir scores novos.
    """
    from app.core.db import task_session_factory
    from app.services.ranking import recompute_all_rankings
    from app.services.sync import sync_all_ranked_difficulties

    async def _run() -> dict:
        from app.core.cache import cache

        await cache._ensure_redis()  # noqa: SLF001
        SessionLocal, close_db = await task_session_factory()
        try:
            async with SessionLocal() as session:
                stats = await sync_all_ranked_difficulties(session, country="BR", max_pages=2)
                ranking = await recompute_all_rankings(session)
                await session.commit()
                return {
                    "scores_fetched": sum(s.fetched for s in stats),
                    "scores_inserted": sum(s.inserted for s in stats),
                    "difficulties_synced": len(stats),
                    "players_updated": ranking.players_updated,
                }
        finally:
            await close_db()

    return asyncio.run(_run())
