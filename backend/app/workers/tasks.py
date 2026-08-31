"""Tarefas Celery — incluindo a pipeline do batch semanal (Plan.md §3.4)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select


@shared_task(name="ping")
def ping() -> str:
    """Sanity check da fila/workers."""
    return "pong"


def _rating_lines(history_rows: list) -> list[str]:
    lines = []
    for h in history_rows[:10]:
        arrow = "⬆️" if (h.total_stars_after or 0) > (h.total_stars_before or 0) else "⬇️"
        lines.append(f"{arrow} `{h.total_stars_before:.2f}★ → {h.total_stars_after:.2f}★`")
    if len(history_rows) > 10:
        lines.append(f"_… e mais {len(history_rows) - 10} mapas_")
    return lines


async def run_weekly_batch() -> dict:
    from app.core.cache import cache, task_redis_client
    from app.core.db import task_session_factory  # engine isolado por loop (tasks celery)

    # O cache._redis global foi criado no processo pai (pré-fork) com conexões
    # de um loop que já fechou; recria no loop desta execução (mesmo padrão do
    # engine do banco). Sem isso: "Event loop is closed" no rate-limiter.
    cache._redis = await task_redis_client()

    SessionLocal, close_db = await task_session_factory()
    from app.integrations.discord import send_batch_report
    from app.models import Batch, BatchKind, RatingHistory
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

            changed = (
                (
                    await session.scalars(
                        select(RatingHistory).where(RatingHistory.batch_id == batch.id)
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
    await send_batch_report(
        {
            "title": "BSBR — Batch semanal concluído",
            "description": "Pipeline de sync, reweight e ranking executada.",
            "fields": {
                **{k: v for k, v in stats.items()},
                "Mudanças de rating": "\n".join(_rating_lines(changed)) or "—",
            },
        }
    )
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
        from app.core.cache import cache, task_redis_client

        cache._redis = await task_redis_client()  # cliente Redis novo no loop atual
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
