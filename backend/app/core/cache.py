"""Cache de aplicação: Redis quando ``REDIS_URL`` está definido,
memória de processo caso contrário (dev local sem serviços).
"""

import asyncio
import time
from typing import Any

import orjson

from app.core.config import get_settings

_MEMORY_STORE: dict[str, tuple[float, bytes]] = {}
_MEMORY_TTL_ORDER: list[str] = []
_MEMORY_MAX_KEYS = 10_000


class Cache:
    def __init__(self) -> None:
        self._redis = None
        self._redis_loop = None
        self._url = get_settings().redis_url

    @property
    def is_redis(self) -> bool:
        return self._redis is not None

    async def _ensure_redis(self):
        """Garante um cliente Redis associado ao event loop atual.

        ``redis.asyncio`` mantém conexões no pool associadas ao loop em que
        foram usadas. Isso importa para o ``TestClient`` do Starlette e para
        tasks Celery que usam ``asyncio.run``: cada execução pode ter um loop
        novo, então um cliente global de um loop anterior não pode ser
        reutilizado.
        """
        if not self._url:
            return

        loop = asyncio.get_running_loop()
        if self._redis is not None and self._redis_loop is loop:
            return

        old_redis = self._redis
        self._redis = None
        self._redis_loop = None
        if old_redis is not None:
            try:
                await old_redis.aclose()
            except Exception:
                # O loop anterior pode já ter sido encerrado; o cliente não
                # será reutilizado, portanto o fechamento é best effort.
                pass

        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(self._url, decode_responses=True)
        self._redis_loop = loop

    async def get_json(self, key: str) -> Any | None:
        if self._url:
            await self._ensure_redis()
        if self._redis is not None:
            raw = await self._redis.get(key)
            return orjson.loads(raw) if raw else None
        self._evict_expired()
        entry = _MEMORY_STORE.get(key)
        return orjson.loads(entry[1]) if entry else None

    async def set_json(self, key: str, value: Any, ttl: int = 60) -> None:
        if self._url:
            await self._ensure_redis()
        payload = orjson.dumps(value)
        if self._redis is not None:
            await self._redis.set(key, payload, ex=ttl)
            return
        if key not in _MEMORY_STORE and len(_MEMORY_STORE) >= _MEMORY_MAX_KEYS:
            oldest = _MEMORY_TTL_ORDER.pop(0)
            _MEMORY_STORE.pop(oldest, None)
        _MEMORY_STORE[key] = (time.monotonic() + ttl, payload)
        _MEMORY_TTL_ORDER.append(key)

    async def invalidate(self, *keys: str) -> None:
        if self._url:
            await self._ensure_redis()
        for key in keys:
            if self._redis is not None:
                await self._redis.delete(key)
            else:
                _MEMORY_STORE.pop(key, None)

    async def invalidate_prefix(self, prefix: str) -> int:
        """Remove todas as chaves com o prefixo dado. Retorna quantas caíram."""
        removed = 0
        if self._url:
            await self._ensure_redis()
        if self._redis is not None:
            async for key in self._redis.scan_iter(match=f"{prefix}*"):
                await self._redis.delete(key)
                removed += 1
        else:
            doomed = [k for k in _MEMORY_STORE if k.startswith(prefix)]
            for k in doomed:
                _MEMORY_STORE.pop(k, None)
            removed = len(doomed)
        return removed

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (exp, _) in _MEMORY_STORE.items() if exp <= now]
        for k in expired:
            _MEMORY_STORE.pop(k, None)


async def task_redis_client():
    """Cliente Redis novo, ligado ao loop da task celery (engine por loop).

    O ``cache._redis`` global é criado no processo pai (pré-fork); as conexões
    ficam presas ao loop que as criou, e as tasks celery rodam ``asyncio.run``
    com um loop novo por execução. Recriar o cliente no loop atual evita o
    ``Event loop is closed`` / ``attached to a different loop`` — o mesmo
    problema que o ``task_session_factory`` resolve para o engine do banco.
    """
    url = get_settings().redis_url
    if not url:
        return None
    import redis.asyncio as aioredis

    return aioredis.from_url(url, decode_responses=True)


cache = Cache()
