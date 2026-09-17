"""Provider A: DuckDuckGo HTML search.

Why DuckDuckGo: it requires no API key, which keeps the baseline system
runnable end-to-end with zero paid credentials (important for a reviewer to
be able to try the project immediately). We use the HTML endpoint
(html.duckduckgo.com/html/), parsing the response with BeautifulSoup, rather
than an unofficial JSON API.

Documented limitations (see README "Provider Abstraction" section):
  * This is an unofficial, undocumented HTML interface, not a stable public
    API. DuckDuckGo can change markup or block scraping traffic at any time
    without notice, and there is no published SLA or rate limit — we apply
    our own conservative client-side pacing via the rate limiter.
  * No image/video/news-specific endpoints are used.
  * Results do not include a reliable published date for most pages.
"""
from __future__ import annotations

import logging
from typing import List
from urllib.parse import parse_qs, urlparse, unquote

import httpx
from bs4 import BeautifulSoup

from app.models.errors import ProviderError
from app.models.search import RawSearchResult
from app.providers.base import SearchProvider
from app.reliability.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger("research_agent.providers.duckduckgo")

_HTML_URL = "https://html.duckduckgo.com/html/"
_LITE_URL = "https://lite.duckduckgo.com/lite/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

_RETRYABLE_STATUS_CODES = {202, 403, 429, 500, 502, 503}


def _extract_destination_url(href: str) -> str:
    """Extract the real destination URL from a DuckDuckGo redirect link."""
    if not href:
        return href
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and "/l/" in parsed.path:
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg")
        if uddg:
            return unquote(uddg[0])
    return href


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    def __init__(self, timeout_seconds: float = 8.0, rate_limiter: TokenBucketRateLimiter | None = None) -> None:
        self._timeout = timeout_seconds
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(rate_per_second=1.0, burst=2)

    async def search(self, query: str, max_results: int) -> List[RawSearchResult]:
        await self._rate_limiter.acquire()
        try:
            results = await self._search_html(query, max_results)
            if results:
                return results
            # 200 OK but zero parseable results: could be a genuinely empty
            # result set OR changed markup. Try the Lite endpoint before
            # giving up; return [] only if Lite also finds nothing.
            logger.info("ddg_html_empty_fallback_lite")
        except ProviderError as exc:
            if not exc.retryable:
                raise
            logger.info("ddg_html_retryable_fallback_lite", extra={"status_code": exc.status_code})
        return await self._search_lite(query, max_results)

    async def _search_html(self, query: str, max_results: int) -> List[RawSearchResult]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=_HEADERS) as client:
                response = await client.post(_HTML_URL, data={"q": query})
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"DuckDuckGo HTML request timed out: {exc}", provider=self.name, retryable=True
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"DuckDuckGo HTML connection failed: {exc}", provider=self.name, retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"DuckDuckGo HTML request failed: {exc}", provider=self.name, retryable=True
            ) from exc

        if response.status_code in _RETRYABLE_STATUS_CODES:
            raise ProviderError(
                f"DuckDuckGo HTML returned {response.status_code}",
                provider=self.name,
                retryable=True,
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ProviderError(
                f"DuckDuckGo HTML unexpected status ({response.status_code})",
                provider=self.name,
                retryable=False,
                status_code=response.status_code,
            )

        results = self._parse_html(response.text, max_results)
        return results

    async def _search_lite(self, query: str, max_results: int) -> List[RawSearchResult]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=_HEADERS) as client:
                response = await client.post(_LITE_URL, data={"q": query})
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"DuckDuckGo Lite request timed out: {exc}", provider=self.name, retryable=True
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"DuckDuckGo Lite connection failed: {exc}", provider=self.name, retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"DuckDuckGo Lite request failed: {exc}", provider=self.name, retryable=True
            ) from exc

        if response.status_code in _RETRYABLE_STATUS_CODES:
            raise ProviderError(
                f"DuckDuckGo Lite returned {response.status_code}",
                provider=self.name,
                retryable=True,
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ProviderError(
                f"DuckDuckGo Lite unexpected status ({response.status_code})",
                provider=self.name,
                retryable=False,
                status_code=response.status_code,
            )

        results = self._parse_lite(response.text, max_results)
        return results

    def _parse_html(self, html: str, max_results: int) -> List[RawSearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: List[RawSearchResult] = []
        for result_div in soup.select("div.result")[:max_results]:
            link = (
                result_div.select_one("a.result__a")
                or result_div.select_one("a.result__url")
            )
            snippet_el = (
                result_div.select_one("a.result__snippet")
                or result_div.select_one(".result__snippet")
                or result_div.select_one("a.result__body")
            )
            if not link:
                continue
            href = link.get("href")
            if not isinstance(href, str):
                continue
            title = link.get_text(strip=True)
            url = _extract_destination_url(href)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title and url:
                results.append(
                    RawSearchResult(provider=self.name, title=title, url=url, snippet=snippet)
                )
        return results

    def _parse_lite(self, html: str, max_results: int) -> List[RawSearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: List[RawSearchResult] = []
        link_tables = soup.select("table.result-link")[:max_results]
        snippets = soup.select("p.result-snippet")
        for idx, table in enumerate(link_tables):
            anchor = table.select_one("a")
            if not anchor:
                continue
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            title = anchor.get_text(strip=True)
            url = _extract_destination_url(href)
            snippet = snippets[idx].get_text(strip=True) if idx < len(snippets) else ""
            if title and url:
                results.append(
                    RawSearchResult(provider=self.name, title=title, url=url, snippet=snippet)
                )
        return results
