import time

from app.reliability.circuit_breaker import CircuitBreaker, CircuitState


def test_breaker_opens_after_threshold_failures():
    breaker = CircuitBreaker(failure_threshold=3, reset_seconds=10)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert not breaker.allow_request()


def test_breaker_stays_closed_below_threshold():
    breaker = CircuitBreaker(failure_threshold=3, reset_seconds=10)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request()


def test_breaker_resets_to_half_open_after_window():
    breaker = CircuitBreaker(failure_threshold=1, reset_seconds=0.05)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    time.sleep(0.1)
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.allow_request()


def test_success_resets_failure_count():
    breaker = CircuitBreaker(failure_threshold=3, reset_seconds=10)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED  # count was reset, so 2 more != threshold of 3
