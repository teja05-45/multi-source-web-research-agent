"""Citation validation: never trust the LLM's citations blindly.

For every claim the LLM produced, this module:
  1. Rejects citation IDs that do not correspond to a real Evidence object
     (the LLM cannot invent an evidence ID that maps to nothing).
  2. Checks lightweight lexical overlap between the claim text and the cited
     evidence passage(s). If overlap is very low, the claim is flagged
     rather than trusted.
  3. Produces a final `support_status` per claim: SUPPORTED, CONTRADICTED
     (if the claim's citations point to evidence flagged as part of a
     detected conflict), or INSUFFICIENT_EVIDENCE (no valid citations, or
     citations too weakly related to the claim text).

Important documented limitation: lexical overlap is a heuristic proxy for
"is this claim actually supported", not a semantic entailment check. It
will miss claims that are correctly paraphrased with no shared words, and
can be fooled by claims that reuse the source's words without accurately
representing its meaning. See README "Citation System" for the full
discussion of why this does not guarantee truth.
"""
from __future__ import annotations

import re

from app.models.claims import Claim, Conflict, SupportStatus, VerifiedClaim
from app.models.evidence import Evidence

_MIN_OVERLAP_RATIO = 0.15


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _lexical_support(claim_text: str, passages: list[str]) -> float:
    claim_tokens = _tokenize(claim_text)
    if not claim_tokens:
        return 0.0
    passage_tokens: set[str] = set()
    for p in passages:
        passage_tokens |= _tokenize(p)
    overlap = claim_tokens & passage_tokens
    return len(overlap) / len(claim_tokens)


def _evidence_ids_in_conflicts(conflicts: list[Conflict]) -> set[str]:
    ids: set[str] = set()
    for c in conflicts:
        ids.update(c.position_a_sources)
        ids.update(c.position_b_sources)
    return ids


def validate_claims(
    claims: list[Claim], evidence_by_id: dict[str, Evidence], conflicts: list[Conflict]
) -> tuple[list[VerifiedClaim], int]:
    """Returns (verified_claims, unsupported_claims_removed_count)."""
    verified: list[VerifiedClaim] = []
    removed = 0
    conflicted_evidence_ids = _evidence_ids_in_conflicts(conflicts)

    for claim in claims:
        valid_citations = [c for c in claim.citation_evidence_ids if c in evidence_by_id]
        invalid_citations = [c for c in claim.citation_evidence_ids if c not in evidence_by_id]

        if not valid_citations:
            removed += 1
            verified.append(
                VerifiedClaim(
                    claim=claim.text,
                    citations=[],
                    support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
                    validator_note=(
                        "No valid citations were provided for this claim"
                        + (f" (invalid IDs: {invalid_citations})" if invalid_citations else "")
                        + "; it was not backed by verifiable evidence and has been flagged rather than trusted."
                    ),
                )
            )
            continue

        passages = [evidence_by_id[c].passage for c in valid_citations]
        support = _lexical_support(claim.text, passages)

        if support < _MIN_OVERLAP_RATIO:
            removed += 1
            verified.append(
                VerifiedClaim(
                    claim=claim.text,
                    citations=valid_citations,
                    support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
                    validator_note=(
                        f"Cited evidence shows low lexical overlap with the claim "
                        f"(overlap ratio {support:.2f} < {_MIN_OVERLAP_RATIO}); "
                        "flagged as weakly supported rather than trusted outright."
                    ),
                )
            )
            continue

        if any(cid in conflicted_evidence_ids for cid in valid_citations):
            verified.append(
                VerifiedClaim(
                    claim=claim.text,
                    citations=valid_citations,
                    support_status=SupportStatus.CONTRADICTED,
                    validator_note="This claim's evidence is involved in a detected source conflict; see conflicts.",
                )
            )
            continue

        note = None
        if invalid_citations:
            note = f"Some cited IDs were invalid and dropped: {invalid_citations}"

        verified.append(
            VerifiedClaim(
                claim=claim.text,
                citations=valid_citations,
                support_status=SupportStatus.SUPPORTED,
                validator_note=note,
            )
        )

    return verified, removed
