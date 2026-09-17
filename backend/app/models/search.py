"""Search-result models: provider-agnostic normalized results."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class RawSearchResult(BaseModel):
    """A single result as returned directly from a provider, pre-normalization."""

    provider: str
    title: str
    url: str
    snippet: str = ""
    published_date: Optional[str] = None


class SearchResult(BaseModel):
    """Provider-agnostic, normalized search result.

    This is the canonical schema the rest of the pipeline operates on.
    Provider provenance is preserved via `providers` (a result can be
    reported by more than one provider after deduplication merges them).
    """

    result_id: str
    providers: list[str] = Field(default_factory=list)
    title: str
    url: str
    canonical_url: str
    domain: str
    snippet: str = ""
    published_date: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duplicate_of: Optional[str] = None
    duplicate_count: int = 0
    relevance_score: float = 0.0
    authority_score: float = 0.0
    freshness_score: float = 0.0
    final_score: float = 0.0

    @staticmethod
    def make_id(canonical_url: str) -> str:
        return hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()[:12]


class FetchedContent(BaseModel):
    """The extracted textual content of a source page, if fetching succeeded."""

    result_id: str
    url: str
    fetched: bool
    text: str = ""
    content_length: int = 0
    truncated: bool = False
    error: Optional[str] = None
