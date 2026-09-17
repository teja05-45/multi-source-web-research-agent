"""Bounded retry with exponential backoff for transient failures.

Only `ProviderError` instances with `retryable=True` are retried (e.g.
timeouts, connection errors, HTTP 429/500/502/503). Permanent failures
(invalid credentials, malformed request) are raised immediately.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

from app.models.errors import ProviderError

logger = logging.getLogger("research_agent.reliability.retry")

T = TypeVar("T")


class RetryExhaustedError(Exception):
    def __init__(self, last_error: Exception, attempts: int) -> None:
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_error}")
        self.last_error = last_error
        self.attempts = attempts


async def retry_with_backoff(
    operation: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    base_delay_seconds: float,
    provider_name: str,
    max_delay_seconds: float = 8.0,
) -> tuple[T, int]:
    """Run `operation`, retrying on retryable ProviderErrors.

    Returns (result, retry_count). Raises the last ProviderError if all
    attempts are exhausted, or re-raises immediately on a non-retryable
    ProviderError.
    """
    attempt = 0
    last_error: Exception | None = None

    while attempt <= max_retries:
        try:
            result = await operation()
            return result, attempt
        except ProviderError as exc:
            last_error = exc
            if not exc.retryable or attempt == max_retries:
                logger.warning(
                    "provider_call_failed_final",
                    extra={
                        "provider": provider_name,
                        "retryable": exc.retryable,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                raise
            delay = min(max_delay_seconds, base_delay_seconds * (2**attempt))
            delay = delay * (0.5 + random.random())  # jitter
            logger.info(
                "provider_call_retry",
                extra={
                    "provider": provider_name,
                    "attempt": attempt,
                    "delay_seconds": round(delay, 3),
                    "error": str(exc),
                },
            )
            await asyncio.sleep(delay)
            attempt += 1

    # Should be unreachable, but keep mypy/type-checkers and defensive coding happy.
    assert last_error is not None
    raise last_error
