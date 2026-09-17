"""Integration tests for provider failure handling.

External HTTP calls are mocked with respx — no live network access is used.
"""
import httpx
import pytest
import respx

from app.models.errors import ProviderError
from app.providers.duckduckgo_provider import DuckDuckGoProvider
from app.providers.tavily_provider import TavilyProvider
from app.reliability.rate_limiter import TokenBucketRateLimiter


def _fast_limiter():
    return TokenBucketRateLimiter(rate_per_second=1000, burst=1000)


@pytest.mark.asyncio
@respx.mock
async def test_duckduckgo_success_parses_results():
    html = """
    <div class="result">
      <a class="result__a" href="https://example.com/a">Result A</a>
      <a class="result__snippet">Snippet A</a>
    </div>
    <div class="result">
      <a class="result__a" href="https://example.com/b">Result B</a>
      <a class="result__snippet">Snippet B</a>
    </div>
    """
    respx.post("https://html.duckduckgo.com/html/").mock(return_value=httpx.Response(200, text=html))
    provider = DuckDuckGoProvider(rate_limiter=_fast_limiter())
    results = await provider.search("test query", max_results=5)
    assert len(results) == 2
    assert results[0].title == "Result A"


@pytest.mark.asyncio
@respx.mock
async def test_duckduckgo_extracts_redirect_destination_url():
    html = """
    <div class="result">
      <a class="result__a"
         href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Farticle%3Fa%3D1">Title</a>
      <a class="result__snippet">Snippet</a>
    </div>
    """
    respx.post("https://html.duckduckgo.com/html/").mock(return_value=httpx.Response(200, text=html))
    provider = DuckDuckGoProvider(rate_limiter=_fast_limiter())
    results = await provider.search("test query", max_results=5)
    assert results[0].url == "https://example.com/article?a=1"


def test_duckduckgo_redirect_extraction_helper():
    from app.providers.duckduckgo_provider import _extract_destination_url

    assert _extract_destination_url(
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.bbc.com%2Fnews"
    ) == "https://www.bbc.com/news"
    assert _extract_destination_url("https://example.com/x") == "https://example.com/x"


@pytest.mark.asyncio
@respx.mock
async def test_duckduckgo_202_falls_back_to_lite():
    respx.post("https://html.duckduckgo.com/html/").mock(return_value=httpx.Response(202))
    lite_html = """
    <table class="result-link"><a href="https://example.com/lite">Lite Result</a></table>
    <p class="result-snippet">Lite snippet</p>
    """
    respx.post("https://lite.duckduckgo.com/lite/").mock(return_value=httpx.Response(200, text=lite_html))
    provider = DuckDuckGoProvider(rate_limiter=_fast_limiter())
    results = await provider.search("test query", max_results=5)
    assert len(results) == 1
    assert results[0].title == "Lite Result"


@pytest.mark.asyncio
@respx.mock
async def test_duckduckgo_429_raises_retryable_provider_error_when_lite_also_blocks():
    respx.post("https://html.duckduckgo.com/html/").mock(return_value=httpx.Response(429))
    respx.post("https://lite.duckduckgo.com/lite/").mock(return_value=httpx.Response(429))
    provider = DuckDuckGoProvider(rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
@respx.mock
async def test_duckduckgo_500_raises_retryable_provider_error():
    respx.post("https://html.duckduckgo.com/html/").mock(return_value=httpx.Response(500))
    respx.post("https://lite.duckduckgo.com/lite/").mock(return_value=httpx.Response(500))
    provider = DuckDuckGoProvider(rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
@respx.mock
async def test_duckduckgo_timeout_raises_retryable_provider_error():
    respx.post("https://html.duckduckgo.com/html/").mock(side_effect=httpx.TimeoutException("timed out"))
    respx.post("https://lite.duckduckgo.com/lite/").mock(side_effect=httpx.TimeoutException("timed out"))
    provider = DuckDuckGoProvider(rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
@respx.mock
async def test_duckduckgo_empty_results_returns_empty_list():
    respx.post("https://html.duckduckgo.com/html/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.post("https://lite.duckduckgo.com/lite/").mock(return_value=httpx.Response(200, text="<html></html>"))
    provider = DuckDuckGoProvider(rate_limiter=_fast_limiter())
    results = await provider.search("test query", max_results=5)
    assert results == []


@pytest.mark.asyncio
async def test_tavily_missing_api_key_is_non_retryable():
    provider = TavilyProvider(api_key=None, rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
@respx.mock
async def test_tavily_auth_failure_is_non_retryable():
    respx.post("https://api.tavily.com/search").mock(return_value=httpx.Response(401))
    provider = TavilyProvider(api_key="fake-key", rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
@respx.mock
async def test_tavily_success_parses_results():
    body = {"results": [{"url": "https://example.com/a", "title": "A", "content": "snippet A"}]}
    respx.post("https://api.tavily.com/search").mock(return_value=httpx.Response(200, json=body))
    provider = TavilyProvider(api_key="fake-key", rate_limiter=_fast_limiter())
    results = await provider.search("test query", max_results=5)
    assert len(results) == 1
    assert results[0].title == "A"


@pytest.mark.asyncio
@respx.mock
async def test_tavily_malformed_json_is_non_retryable():
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})
    )
    provider = TavilyProvider(api_key="fake-key", rate_limiter=_fast_limiter())
    with pytest.raises(ProviderError) as exc_info:
        await provider.search("test query", max_results=5)
    assert exc_info.value.retryable is False
