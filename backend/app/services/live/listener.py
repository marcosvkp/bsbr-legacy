"""Listener dos feeds WebSocket de scores ao vivo (ScoreSaber e BeatLeader).

Loop asyncio por fonte: conecta, consome mensagens, publica no bus Redis.
Reconexão com backoff exponencial (1s -> 60s); loga sempre a transição.
"""

from __future__ import annotations

import asyncio
import logging

import websockets

from .bus import publish
from .messages import parse_message

logger = logging.getLogger(__name__)

DEFAULT_WS_URLS = {
    "scoresaber": "wss://scoresaber.com/ws",
    "beatleader": "wss://sockets.api.beatleader.com/scores",
}

MAX_BACKOFF_SECONDS = 60
PING_INTERVAL_SECONDS = 30


class ScorefeedListener:
    def __init__(self, source: str, url: str | None = None):
        self.source = source
        self.url = url or DEFAULT_WS_URLS.get(source)
        if self.url is None:
            raise ValueError(f"fonte desconhecida: {source}")

    async def _handle_message(self, payload: str) -> None:
        live = parse_message(self.source, payload)
        if live is None:
            return
        await publish(live)

    async def run_once(self) -> bool:
        """Conecta e consome até a conexão cair; False em erro de conexão."""
        try:
            async with websockets.connect(
                self.url, ping_interval=PING_INTERVAL_SECONDS, ping_timeout=20,
                open_timeout=15, close_timeout=5, max_queue=500,
            ) as ws:
                logger.info("[%s] conectado: %s", self.source, self.url)
                async for raw in ws:
                    try:
                        await self._handle_message(raw)
                    except Exception:
                        logger.exception("[%s] erro ao processar mensagem", self.source)
            logger.info("[%s] conexão fechada", self.source)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[%s] erro de conexão: %s", self.source, exc)
            return False
        return True

    async def run(self) -> None:
        """Loop com reconexão e backoff exponencial."""
        backoff = 1
        while True:
            ok = await self.run_once()
            if ok:
                backoff = 1
                continue
            logger.info("[%s] reconectando em %ss...", self.source, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


def build_listeners(sources: list[str] | None = None) -> list[ScorefeedListener]:
    """Fontes ativas: ScoreSaber sempre; BeatLeader só se habilitado
    (wss://sockets.api.beatleader.com/scores — validado 2026-08-29)."""
    from app.core.config import get_settings

    settings = get_settings()
    if sources is None:
        sources = ["scoresaber"]
        if settings.live_beatleader_enabled:
            sources.append("beatleader")
    listeners = []
    for source in sources:
        if source not in DEFAULT_WS_URLS:
            logger.warning("fonte de scorefeed desconhecida: %s (ignorada)", source)
            continue
        listeners.append(ScorefeedListener(source))
    return listeners


async def run_all(listeners: list[ScorefeedListener] | None = None) -> None:
    listeners = listeners or build_listeners()
    if not listeners:
        logger.warning("nenhuma fonte de scorefeed configurada — encerrando")
        return
    await asyncio.gather(*(l.run() for l in listeners))
