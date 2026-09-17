"""Normalize raw provider results into the canonical SearchResult schema.

Canonicalization rules applied here (see also deduplicator.py which uses
`canonical_url` as its primary key):
  1. lowercase the scheme and host
  2. strip known tracking query parameters (utm_*, gclid, fbclid, ref, etc.)
  3. remove the URL fragment (#...)
  4. remove a single trailing slash on the path (except root "/")
  5. drop default ports (80 for http, 443 for https)
"""
from __future__ import annotations

from typing import Iterable, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.models.search import RawSearchResult, SearchResult

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "ref_src",
    "igshid",
    "mc_cid",
    "mc_eid",
    "spm",
    "__cf_chl_jschl_tk__",
}


def canonicalize_url(url: str) -> str:
    """Deterministically canonicalize a URL for deduplication purposes."""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "http").lower()
    netloc = parsed.netloc.lower()

    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[: -len(":80")]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[: -len(":443")]

    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept_params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower in _TRACKING_PARAMS or any(key_lower.startswith(p) for p in _TRACKING_PARAM_PREFIXES):
            continue
        kept_params.append((key, value))
    kept_params.sort()
    query = urlencode(kept_params)

    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc.split(":")[0]


def normalize_results(raw_results: Iterable[RawSearchResult]) -> List[SearchResult]:
    """Convert raw provider results into normalized SearchResult objects.

    Provider provenance is retained. This function does NOT deduplicate —
    that is a separate, explicit stage (see deduplicator.py) so behavior is
    independently testable.
    """
    normalized: List[SearchResult] = []
    for raw in raw_results:
        if not raw.url or not raw.title:
            continue
        canonical = canonicalize_url(raw.url)
        normalized.append(
            SearchResult(
                result_id=SearchResult.make_id(canonical),
                providers=[raw.provider],
                title=raw.title.strip(),
                url=raw.url,
                canonical_url=canonical,
                domain=extract_domain(raw.url),
                snippet=raw.snippet.strip(),
                published_date=raw.published_date,
            )
        )
    return normalized
