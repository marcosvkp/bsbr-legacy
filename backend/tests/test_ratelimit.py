"""Testes do rate limiter de janela deslizante (busy-loop do acquire)."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.core.ratelimit import SlidingWindowLimiter


async def test_acquire_sleeps_when_window_full():
    """Sem o sleep, acquire() vira busy-loop no Redis quando a janela enche."""
    limiter = SlidingWindowLimiter("test-sleep", max_calls=1, period_seconds=1)

    # consome a única vaga
    assert await limiter.try_acquire() == 0.0
    assert await limiter.try_acquire() > 0.0  # janela cheia

    t0 = time.monotonic()
    # acquire() deve bloquear (sleep) até a janela deslizar — não girar
    await asyncio.wait_for(limiter.acquire(), timeout=2.0)
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.9, f"acquire deveria esperar ~1s, voltou em {elapsed:.2f}s"


async def test_try_acquire_is_non_blocking():
    limiter = SlidingWindowLimiter("test-nb", max_calls=2, period_seconds=60)
    assert await limiter.try_acquire() == 0.0
    assert await limiter.try_acquire() == 0.0
    assert await limiter.try_acquire() > 0.0  # 3ª tentativa: não bloqueia
