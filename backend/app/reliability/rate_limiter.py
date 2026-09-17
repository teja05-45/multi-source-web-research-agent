"""A simple token-bucket rate limiter usable per-provider or globally.

This protects both outbound calls to third-party APIs (staying under their
published rate limits) and can be reused to throttle inbound API usage if
needed. It is intentionally in-process/in-memory: sufficient for a
single-instance deployment; a multi-instance deployment would back this with
Redis (documented as a known limitation in the README).
"""
from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    def __init__(self, rate_per_second: float, burst: int) -> None:
        self._rate = rate_per_second
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                self._tokens = 0
                self._last_refill = time.monotonic()
            else:
                self._tokens -= 1
