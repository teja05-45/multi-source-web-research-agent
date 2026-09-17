"""Provider C: Brave Search API.

Brave Search provides a privacy-focused web search API with a documented,
versioned REST interface. Requires BRAVE_API_KEY. A free tier is available.

Documented limitations:
  * Free tier has a monthly request quota; production usage may require a
    paid plan.
  * Results do not include full page content; only title, URL, description,
    and optional metadata are returned.
"""
from __future__ import annotations

import logging
from typing import List

import httpx

from app.models.errors import ProviderError
from app.models.search import RawSearchResult
from app.providers.base import SearchProvider
from app.reliability.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger("research_agent.providers.brave")

_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
}


class BraveProvider(SearchProvider):
    name = "brave"

    def __init__(
        self,
        api_key: str | None,
        timeout_seconds: float = 8.0,
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(rate_per_second=2.0, burst=3)

    async def search(self, query: str, max_results: int) -> List[RawSearchResult]:
        if not self._api_key:
            raise ProviderError(
                "BRAVE_API_KEY is not configured", provider=self.name, retryable=False
            )

        await self._rate_limiter.acquire()

        headers = {**_HEADERS, "X-Subscription-Token": self._api_key}
        params: dict[str, str | int] = {"q": query, "count": max_results, "search_lang": "en"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_SEARCH_URL, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Brave request timed out: {exc}", provider=self.name, retryable=True
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Brave connection failed: {exc}", provider=self.name, retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Brave request failed: {exc}", provider=self.name, retryable=True
            ) from exc

        if response.status_code in (401, 403):
            raise ProviderError(
                "Brave authentication failed - check BRAVE_API_KEY",
                provider=self.name,
                retryable=False,
                status_code=response.status_code,
            )
        if response.status_code == 429:
            raise ProviderError(
                "Brave rate limit exceeded (429)", provider=self.name, retryable=True, status_code=429
            )
        if response.status_code in (500, 502, 503):
            raise ProviderError(
                f"Brave server error ({response.status_code})",
                provider=self.name,
                retryable=True,
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ProviderError(
                f"Brave unexpected status ({response.status_code})",
                provider=self.name,
                retryable=False,
                status_code=response.status_code,
            )

        try:
            data = response.json()
            web_results = data.get("web", {}).get("results", [])
        except Exception as exc:
            raise ProviderError(
                f"Failed to parse Brave response: {exc}", provider=self.name, retryable=False
            ) from exc

        results: List[RawSearchResult] = []
        for item in web_results[:max_results]:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            snippet = item.get("description", "") or ""
            results.append(
                RawSearchResult(
                    provider=self.name,
                    title=title,
                    url=url,
                    snippet=snippet,
                    published_date=item.get("age"),
                )
            )
        return results

    async def health_check(self) -> bool:
        return bool(self._api_key)
