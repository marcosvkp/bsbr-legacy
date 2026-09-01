"""Rate limiter de janela deslizante compartilhado entre processos.

Usa Redis (ZSET de timestamps) quando disponível — o limite vale para API,
workers e beat juntos. Sem Redis, cai para memória do processo (dev).
"""

import asyncio
import time
from collections import deque
from typing import Any

from app.core.cache import cache


class SlidingWindowLimiter:
    def __init__(self, name: str, max_calls: int, period_seconds: int) -> None:
        self.name = f"ratelimit:{name}"
        self.max_calls = max_calls
        self.period = period_seconds
        self._local: deque[float] = deque()

    @property
    def _redis(self) -> Any:
        """Cliente Redis atual; resolvido pelo cache por event loop."""
        return cache._redis  # noqa: SLF001

    @property
    def is_shared(self) -> bool:
        return cache._redis is not None  # noqa: SLF001

    async def acquire(self) -> float:
        """Bloqueia até uma vaga abrir na janela. Retorna segundos esperados.

        Sem o sleep, um excesso de chamadas vira busy-loop no Redis (e o
        request fica pendurado para sempre — a coleta global/remap do reweight
        faz ~1000 chamadas e estoura a janela de 350/min).
        """
        while True:
            waited = await self.try_acquire()
            if waited == 0.0:
                return 0.0
            await asyncio.sleep(waited)

    async def try_acquire(self) -> float:
        """Tentativa única não-bloqueante: 0.0 = adquiriu; >0 = segundos até a próxima vaga."""
        return await self._try_acquire_once()

    async def reset(self) -> None:
        """Zera o estado da janela (isolamento entre testes/execuções).

        Sem Redis, limpa o deque local. Com Redis, apaga o ZSET — usado pelos
        testes com REDIS_URL (CI), onde o estado vive no Redis e não no
        registry em memória do chamador.
        """
        if cache._url:  # noqa: SLF001
            await cache._ensure_redis()
        redis = self._redis
        if redis is not None:
            await redis.delete(self.name)
        else:
            self._local.clear()

    async def _try_acquire_once(self) -> float:
        now = time.time()
        window_start = now - self.period

        if cache._url:  # noqa: SLF001
            await cache._ensure_redis()
        redis = self._redis
        if redis is not None:
            pipe = redis.pipeline()
            pipe.zremrangebyscore(self.name, "-inf", window_start)
            pipe.zcard(self.name)
            _, count = await pipe.execute()
            if count < self.max_calls:
                await redis.zadd(self.name, {str(now): now})
                await redis.expire(self.name, self.period)
                return 0.0
            oldest = await redis.zrange(self.name, 0, 0, withscores=True)
            if not oldest:
                return 0.0
            return float(oldest[0][1]) + self.period - now

        while self._local and self._local[0] <= window_start:
            self._local.popleft()
        if len(self._local) < self.max_calls:
            self._local.append(now)
            return 0.0
        return self._local[0] + self.period - now
