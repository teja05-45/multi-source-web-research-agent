"""Request-side models: the incoming research question and its plan."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ResearchRequest(BaseModel):
    """Validated payload for POST /api/research."""

    question: str = Field(..., min_length=3, max_length=1000)
    max_sources: int = Field(default=8, ge=1, le=20)
    providers: Optional[List[str]] = Field(
        default=None,
        description="Subset of provider names to use (defaults to all enabled providers).",
    )
    depth: str = Field(default="standard", description="'quick' or 'standard'")

    @field_validator("question")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty or whitespace-only")
        return v

    @field_validator("depth")
    @classmethod
    def _validate_depth(cls, v: str) -> str:
        allowed = {"quick", "standard"}
        if v not in allowed:
            raise ValueError(f"depth must be one of {allowed}")
        return v


class ResearchPlan(BaseModel):
    """Structured output of the planning stage."""

    original_question: str
    subquestions: List[str] = Field(default_factory=list)
    used_fallback: bool = Field(
        default=False, description="True if planning failed and a deterministic fallback was used."
    )

    @field_validator("subquestions")
    @classmethod
    def _dedupe_and_cap(cls, v: List[str]) -> List[str]:
        seen = set()
        deduped = []
        for q in v:
            q = q.strip()
            key = q.lower()
            if q and key not in seen:
                seen.add(key)
                deduped.append(q)
        return deduped[:6]
