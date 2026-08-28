"""Bus de scores ao vivo no Redis (recents + pub/sub para o endpoint WS).

Sem Redis (dev), o bus fica inerte mas não quebra: os métodos retornam no-op.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.core.db import SessionLocal

from .messages import LiveScore
from .persist import persist_live_score

logger = logging.getLogger(__name__)

RECENTS_KEY = "bsbr:live:recents"
CHANNEL = "bsbr:live"
RECENTS_WINDOW_SECONDS = 2 * 60 * 60  # janela de 2h
RECENTS_MAX = 50

_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        url = get_settings().redis_url
        if url:
            import redis.asyncio as aioredis

            _redis = aioredis.from_url(url, decode_responses=True)
    return _redis


async def publish(live: LiveScore) -> None:
    """Persiste + registra nos recents + notifica o canal."""
    try:
        async with SessionLocal() as session:
            outcome = await persist_live_score(session, live)
    except Exception:
        logger.exception("falha ao persistir score ao vivo")
        outcome = {"error": "persist_failed"}

    # Score fora do catálogo ranqueado: não vai para o feed nem para os recents
    if isinstance(outcome, dict) and outcome.get("ignored"):
        return

    redis = _get_redis()
    if redis is None:
        return

    # Enriquece com o PP calculado na persistência (curva do BSBR)
    if live.pp is None and isinstance(outcome, dict) and outcome.get("pp") is not None:
        live.pp = float(outcome["pp"])

    payload = live.to_dict()
    payload["outcome"] = outcome
    # Campos enriquecidos do catálogo (map_hash/cover/avatar) para a UI
    payload.update(
        {
            k: v
            for k, v in outcome.items()
            if k in ("map_hash", "map_name", "cover_url", "avatar_url", "difficulty_name")
        }
    )
    import orjson

    member = orjson.dumps(payload).decode()
    try:
        async with redis.pipeline(transaction=False) as pipe:
            pipe.zadd(RECENTS_KEY, {member: live.time_set.timestamp()})
            pipe.zremrangebyscore(
                RECENTS_KEY, "-inf", live.time_set.timestamp() - RECENTS_WINDOW_SECONDS
            )
            pipe.zremrangebyrank(RECENTS_KEY, 0, -(RECENTS_MAX + 1))
            await pipe.execute()
        await redis.publish(CHANNEL, member)
    except Exception:
        logger.exception("falha ao publicar score ao vivo no redis")


async def recent_scores(limit: int = 20) -> list[dict]:
    """Últimos scores ao vivo (mais recentes primeiro)."""
    redis = _get_redis()
    if redis is None:
        return []
    try:
        raw = await redis.zrevrange(RECENTS_KEY, 0, limit - 1)
    except Exception:
        logger.exception("falha ao ler recents")
        return []
    import orjson

    items = []
    for member in raw:
        try:
            items.append(orjson.loads(member))
        except (ValueError, TypeError):
            continue
    return items
