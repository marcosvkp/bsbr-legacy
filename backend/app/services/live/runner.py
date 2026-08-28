"""Entrypoint do serviço de scorefeed ao vivo (`python -m app.services.live.runner`)."""

from __future__ import annotations

import asyncio
import logging

from .listener import build_listeners, run_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    listeners = build_listeners()
    logger.info("iniciando %d listener(s) de scorefeed ao vivo", len(listeners))
    await run_all(listeners)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("encerrado pelo usuário")
