import pytest

from app.models.errors import ProviderError
from app.reliability.retry import retry_with_backoff


@pytest.mark.asyncio
async def test_retries_transient_error_until_success():
    attempts = {"count": 0}

    async def flaky_op():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ProviderError("temporary", provider="test", retryable=True)
        return "ok"

    result, retries = await retry_with_backoff(
        flaky_op, max_retries=5, base_delay_seconds=0.001, provider_name="test"
    )
    assert result == "ok"
    assert retries == 2
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_does_not_retry_non_retryable_error():
    attempts = {"count": 0}

    async def bad_op():
        attempts["count"] += 1
        raise ProviderError("auth failed", provider="test", retryable=False)

    with pytest.raises(ProviderError):
        await retry_with_backoff(bad_op, max_retries=5, base_delay_seconds=0.001, provider_name="test")
    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_gives_up_after_max_retries():
    attempts = {"count": 0}

    async def always_fails():
        attempts["count"] += 1
        raise ProviderError("still failing", provider="test", retryable=True)

    with pytest.raises(ProviderError):
        await retry_with_backoff(always_fails, max_retries=2, base_delay_seconds=0.001, provider_name="test")
    assert attempts["count"] == 3  # initial + 2 retries
