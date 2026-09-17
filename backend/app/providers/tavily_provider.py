"""Provider B: Tavily Search API.

Why Tavily: it is purpose-built for LLM/RAG use cases, returns clean
pre-summarized snippets and (optionally) full page content in one call, and
has an official, documented, versioned JSON API with clear rate limits.
Requires TAVILY_API_KEY.

Documented limitations (see README "Provider Abstraction" section):
  * Free tier has a monthly request quota; production usage requires a paid
    plan (see https://tavily.com/ for current pricing/limits at time of
    integration).
  * Search depth ("basic" vs "advanced") trades cost for result quality;
    this integration uses "basic" by default to control cost.
  * Like all providers, coverage is not guaranteed to be complete or
    unbiased.
"""
from __future__ import annotations

import logging
from typing import List

import httpx

from app.models.errors import ProviderError
from app.models.search import RawSearchResult
from app.providers.base import SearchProvider
from app.reliability.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger("research_agent.providers.tavily")

_SEARCH_URL = "https://api.tavily.com/search"


class TavilyProvider(SearchProvider):
    name = "tavily"

    def __init__(
        self,
        api_key: str | None,
        timeout_seconds: float = 8.0,
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(rate_per_second=1.0, burst=3)

    async def search(self, query: str, max_results: int) -> List[RawSearchResult]:
        if not self._api_key:
            # Missing credentials is a permanent (non-retryable) failure.
            raise ProviderError(
                "TAVILY_API_KEY is not configured", provider=self.name, retryable=False
            )

        await self._rate_limiter.acquire()

        payload = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(_SEARCH_URL, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Tavily request timed out: {exc}", provider=self.name, retryable=True
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Tavily connection failed: {exc}", provider=self.name, retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Tavily request failed: {exc}", provider=self.name, retryable=True
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            raise ProviderError(
                "Tavily authentication failed - check TAVILY_API_KEY",
                provider=self.name,
                retryable=False,
                status_code=response.status_code,
            )
        if response.status_code == 429:
            raise ProviderError(
                "Tavily rate limit exceeded (429)", provider=self.name, retryable=True, status_code=429
            )
        if response.status_code in (500, 502, 503):
            raise ProviderError(
                f"Tavily server error ({response.status_code})",
                provider=self.name,
                retryable=True,
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ProviderError(
                f"Tavily unexpected status ({response.status_code})",
                provider=self.name,
                retryable=False,
                status_code=response.status_code,
            )

        try:
            data = response.json()
            raw_items = data.get("results", [])
        except Exception as exc:
            raise ProviderError(
                f"Failed to parse Tavily response: {exc}", provider=self.name, retryable=False
            ) from exc

        results: List[RawSearchResult] = []
        for item in raw_items[:max_results]:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            results.append(
                RawSearchResult(
                    provider=self.name,
                    title=title,
                    url=url,
                    snippet=item.get("content", "") or "",
                    published_date=item.get("published_date"),
                )
            )
        return results

    async def health_check(self) -> bool:
        return bool(self._api_key)
