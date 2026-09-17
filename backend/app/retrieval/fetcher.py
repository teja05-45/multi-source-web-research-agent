"""Content fetcher: retrieves full page content for top-ranked sources.

Search snippets are short and often insufficient to ground a claim
accurately, so for the top-N ranked sources we fetch the actual page and
extract readable text (see extractor.py) rather than relying on the
provider's snippet alone.

Safety and robustness:
  * every URL is checked with app.security.url_safety.is_safe_to_fetch
    before any request is made (SSRF mitigation)
  * bounded timeout and bounded response size
  * only http(s) responses with a text-like content-type are processed
  * failures (timeout, 4xx/5xx, disallowed URL, oversized/binary content)
    are captured per-URL and do not abort the batch — the affected source
    simply falls back to its search snippet as evidence text

Known limitations (documented in README "Content Fetching"):
  * no JavaScript rendering — client-side-rendered pages will yield little
    or no extractable text
  * no robots.txt handling (see README for the trade-off discussion)
  * paywalled pages typically extract to near-empty or teaser text
  * PDFs are not parsed; the raw content-type is detected and skipped
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import Settings
from app.models.search import FetchedContent, SearchResult
from app.retrieval.extractor import extract_readable_text
from app.security.url_safety import is_safe_to_fetch

logger = logging.getLogger("research_agent.retrieval.fetcher")

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ResearchLensBot/1.0; +https://example.com/bot)"}
_ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


async def _fetch_one(client: httpx.AsyncClient, result: SearchResult, settings: Settings) -> FetchedContent:
    safe, reason = is_safe_to_fetch(result.url, allow_private_network=settings.allow_private_network_fetch)
    if not safe:
        logger.warning("fetch_blocked", extra={"url": result.url, "reason": reason})
        return FetchedContent(result_id=result.result_id, url=result.url, fetched=False, error=f"blocked:{reason}")

    try:
        async with client.stream("GET", result.url, headers=_HEADERS, timeout=settings.fetch_timeout_seconds) as response:
            content_type = response.headers.get("content-type", "")
            if not any(ct in content_type for ct in _ALLOWED_CONTENT_TYPES):
                return FetchedContent(
                    result_id=result.result_id,
                    url=result.url,
                    fetched=False,
                    error=f"unsupported_content_type:{content_type or 'unknown'}",
                )
            if response.status_code != 200:
                return FetchedContent(
                    result_id=result.result_id,
                    url=result.url,
                    fetched=False,
                    error=f"http_status:{response.status_code}",
                )

            chunks: list[bytes] = []
            total = 0
            truncated = False
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > settings.max_fetch_content_bytes:
                    truncated = True
                    break
                chunks.append(chunk)
            raw_bytes = b"".join(chunks)
    except httpx.TimeoutException:
        return FetchedContent(result_id=result.result_id, url=result.url, fetched=False, error="timeout")
    except httpx.HTTPError as exc:
        return FetchedContent(result_id=result.result_id, url=result.url, fetched=False, error=f"http_error:{exc}")

    try:
        html = raw_bytes.decode("utf-8", errors="replace")
        text = extract_readable_text(html)
    except Exception as exc:  # defensive: never let extraction crash the batch
        return FetchedContent(result_id=result.result_id, url=result.url, fetched=False, error=f"extraction_error:{exc}")

    return FetchedContent(
        result_id=result.result_id,
        url=result.url,
        fetched=True,
        text=text,
        content_length=len(text),
        truncated=truncated,
    )


async def _fetch_one_with_retry(
    client: httpx.AsyncClient, result: SearchResult, settings: Settings, max_retries: int = 1
) -> FetchedContent:
    """Fetch with bounded retry for transient errors."""
    last_error = None
    for attempt in range(max_retries + 1):
        fetched = await _fetch_one(client, result, settings)
        if fetched.fetched:
            return fetched
        if fetched.error and ("timeout" in fetched.error or "http_error" in fetched.error):
            last_error = fetched
            if attempt < max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
        return fetched  # non-retryable failure
    return last_error or FetchedContent(
        result_id=result.result_id, url=result.url, fetched=False, error="exhausted_retries"
    )


async def fetch_contents(
    results: list[SearchResult], settings: Settings, max_concurrency: int
) -> dict[str, FetchedContent]:
    """Fetch content for the given (already-ranked, already-truncated-to-top-N) results."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _bounded(client: httpx.AsyncClient, result: SearchResult) -> FetchedContent:
        async with semaphore:
            return await _fetch_one_with_retry(client, result, settings)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        fetched = await asyncio.gather(*(_bounded(client, r) for r in results)) if results else []

    return {f.result_id: f for f in fetched}
