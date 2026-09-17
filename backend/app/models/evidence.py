"""The Evidence model: the core unit passed into synthesis.

This is the most important architectural decision in this system: the LLM
never sees raw search results or entire web pages. It only ever sees a
curated list of Evidence objects, each traceable back to exactly one
retrieved, ranked, and (where possible) fetched source.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    evidence_id: str
    source_id: str  # references SearchResult.result_id
    url: str
    title: str
    domain: str
    passage: str = Field(..., description="Short, relevant excerpt used as grounding text.")
    relevance_score: float = 0.0
    authority_score: float = 0.0
    freshness_score: float = 0.0
    from_fetched_content: bool = Field(
        default=False, description="True if extracted from fetched page content rather than just a snippet."
    )
