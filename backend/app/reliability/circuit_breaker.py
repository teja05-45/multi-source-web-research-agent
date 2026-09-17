"""A minimal per-provider circuit breaker.

After `failure_threshold` consecutive failures, the breaker "opens" and
short-circuits further calls to that provider for `reset_seconds`, avoiding
wasted latency hammering a provider that is clearly down. After the reset
window elapses, the breaker moves to "half-open" and allows one trial call.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int
    reset_seconds: float
    _failure_count: int = field(default=0, init=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.reset_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def allow_request(self) -> bool:
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()


class CircuitBreakerRegistry:
    """Keeps one breaker per provider name."""

    def __init__(self, failure_threshold: int, reset_seconds: float) -> None:
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, provider_name: str) -> CircuitBreaker:
        if provider_name not in self._breakers:
            self._breakers[provider_name] = CircuitBreaker(
                failure_threshold=self._failure_threshold,
                reset_seconds=self._reset_seconds,
            )
        return self._breakers[provider_name]
