import httpx
import pytest
import respx

from app.models.errors import ProviderError
from app.providers.brave_provider import BraveProvider
from app.reliability.rate_limiter import TokenBucketRateLimiter


def _fast_limiter():
    return TokenBucketRateLimiter(rate_per_second=1000, burst=1000)


@pytest.mark.asyncio
async def test_brave_missing_api_key_is_non_retryable():
    provider = BraveProvider(api_key=None, rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
@respx.mock
async def test_brave_success_parses_results():
    body = {"web": {"results": [{"url": "https://example.com/a", "title": "A", "description": "snippet A"}]}}
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(200, json=body)
    )
    provider = BraveProvider(api_key="fake-key", rate_limiter=_fast_limiter())
    results = await provider.search("test query", max_results=5)
    assert len(results) == 1
    assert results[0].title == "A"
    assert results[0].snippet == "snippet A"


@pytest.mark.asyncio
@respx.mock
async def test_brave_auth_failure_is_non_retryable():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(return_value=httpx.Response(401))
    provider = BraveProvider(api_key="fake-key", rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
@respx.mock
async def test_brave_rate_limit_is_retryable():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(return_value=httpx.Response(429))
    provider = BraveProvider(api_key="fake-key", rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
@respx.mock
async def test_brave_server_error_is_retryable():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(return_value=httpx.Response(503))
    provider = BraveProvider(api_key="fake-key", rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
@respx.mock
async def test_brave_malformed_json_is_non_retryable():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})
    )
    provider = BraveProvider(api_key="fake-key", rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is False