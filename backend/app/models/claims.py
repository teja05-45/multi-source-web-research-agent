"""Claim / verification / conflict models."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SupportStatus(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Claim(BaseModel):
    """A single factual claim produced during synthesis, prior to validation."""

    claim_id: str
    text: str
    citation_evidence_ids: List[str] = Field(default_factory=list)


class VerifiedClaim(BaseModel):
    """A claim after citation validation / verification."""

    claim: str
    citations: List[str] = Field(default_factory=list)
    support_status: SupportStatus
    validator_note: Optional[str] = Field(
        default=None,
        description="Explains why a claim was flagged, downgraded, or qualified.",
    )


class Conflict(BaseModel):
    """An explicit disagreement between two or more sources."""

    topic: str
    position_a: str
    position_a_sources: List[str]
    position_b: str
    position_b_sources: List[str]
    possible_explanation: Optional[str] = Field(
        default=None,
        description="Only populated when the evidence itself suggests a reason (e.g. differing dates).",
    )


class Uncertainty(BaseModel):
    description: str
    reason: str  # e.g. "no_sources_found", "provider_failure", "low_source_diversity", "unverified_claim"
