"""Final API response schema."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.claims import Conflict, Uncertainty, VerifiedClaim


class SourceSummary(BaseModel):
    source_id: str
    title: str
    url: str
    domain: str
    providers: List[str]
    duplicate_count: int = 0
    final_score: float = 0.0
    fetched: bool = False


class ProviderOutcome(BaseModel):
    name: str
    succeeded: bool
    result_count: int = 0
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    retries: int = 0


class ResearchTrace(BaseModel):
    request_id: str
    subqueries: int
    providers_attempted: int
    providers_succeeded: int
    provider_outcomes: List[ProviderOutcome] = Field(default_factory=list)
    results_retrieved: int
    duplicates_removed: int
    sources_fetched: int
    evidence_items: int
    conflicts_detected: int
    unsupported_claims_removed: int = 0
    citation_coverage: float = 0.0
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    total_latency_ms: Optional[float] = None


class ResearchReport(BaseModel):
    request_id: str
    question: str
    answer: str
    key_claims: List[VerifiedClaim] = Field(default_factory=list)
    sources: List[SourceSummary] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)
    uncertainties: List[Uncertainty] = Field(default_factory=list)
    research_trace: ResearchTrace
    degraded: bool = Field(
        default=False,
        description="True if the report was produced with reduced source coverage (e.g. a provider failed).",
    )


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    request_id: Optional[str] = None
