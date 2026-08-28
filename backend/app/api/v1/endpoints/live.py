"""Scores ao vivo: GET /live/recent + WebSocket /api/v1/ws/live.

O WebSocket repassa os scores publicados pelo listener no Redis (pub/sub);
na conexão, envia também os últimos scores para o cliente renderizar a tela.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.services.live.bus import RECENTS_KEY, recent_scores

router = APIRouter()


@router.get("/live/recent")
async def live_recent(limit: int = Query(20, ge=1, le=50)) -> dict:
    """Últimos scores ao vivo capturados pelo scorefeed."""
    return {"items": await recent_scores(limit)}


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    """Stream em tempo real dos scores ao vivo (ScoreSaber + BeatLeader)."""
    await websocket.accept()
    try:
        # Estado inicial: últimos scores para o cliente não ficar em branco
        for item in await recent_scores(20):
            await websocket.send_text(__import__("orjson").dumps(item).decode())
    except Exception:
        pass

    url = get_settings().redis_url
    if not url:
        await websocket.close(code=1011, reason="redis indisponível")
        return

    import redis.asyncio as aioredis

    redis = aioredis.from_url(url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("bsbr:live")
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe("bsbr:live")
        await pubsub.close()
        await redis.aclose()
