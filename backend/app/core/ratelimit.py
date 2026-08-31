"""Rate limiter de janela deslizante compartilhado entre processos.

Usa Redis (ZSET de timestamps) quando disponível — o limite vale para API,
workers e beat juntos. Sem Redis, cai para memória do processo (dev).
"""

import time
from collections import deque

from app.core.cache import cache


class SlidingWindowLimiter:
    def __init__(self, name: str, max_calls: int, period_seconds: int) -> None:
        self.name = f"ratelimit:{name}"
        self.max_calls = max_calls
        self.period = period_seconds
        self._local: deque[float] = deque()
        self._redis = cache._redis  # noqa: SLF001 — mesma infra de cache

    @property
    def is_shared(self) -> bool:
        return self._redis is not None

    async def acquire(self) -> float:
        """Bloqueia até uma vaga abrir na janela. Retorna segundos esperados."""
        while True:
            waited = await self.try_acquire()
            if waited == 0.0:
                return 0.0

    async def try_acquire(self) -> float:
        """Tentativa única não-bloqueante: 0.0 = adquiriu; >0 = segundos até a próxima vaga."""
        return await self._try_acquire_once()

    async def _try_acquire_once(self) -> float:
        now = time.time()
        window_start = now - self.period

        if self._redis is not None:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(self.name, "-inf", window_start)
            pipe.zcard(self.name)
            _, count = await pipe.execute()
            if count < self.max_calls:
                await self._redis.zadd(self.name, {str(now): now})
                await self._redis.expire(self.name, self.period)
                return 0.0
            oldest = await self._redis.zrange(self.name, 0, 0, withscores=True)
            if not oldest:
                return 0.0
            return float(oldest[0][1]) + self.period - now

        while self._local and self._local[0] <= window_start:
            self._local.popleft()
        if len(self._local) < self.max_calls:
            self._local.append(now)
            return 0.0
        return self._local[0] + self.period - now
