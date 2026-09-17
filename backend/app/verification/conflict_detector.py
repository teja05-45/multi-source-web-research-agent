"""Deterministic conflict detection over evidence passages.

This is intentionally NOT an LLM call: it looks for evidence passages from
different domains that mention the same nearby number/quantity phrase with
materially different values (e.g. "500 employees" vs "700 employees").
This catches the clearest, most checkable class of conflicts (numeric
factual disagreement) without asking the LLM to "notice" contradictions,
which is unreliable and unverifiable.

This is explicitly a heuristic, not an exhaustive contradiction detector —
documented as a known limitation. It will not catch conflicts that require
semantic understanding beyond number/keyword proximity (e.g. two sources
disagreeing about the *interpretation* of a fact rather than a number).
"""
from __future__ import annotations

import re
from itertools import combinations

from app.models.claims import Conflict
from app.models.evidence import Evidence

# Pattern 1: number with built-in quantifier (e.g. "40%", "$3 million", "70 percent")
_QUANTIFIED_PATTERN = re.compile(
    r"(?P<number>\$?\d[\d,]*\.?\d*)\s*(?P<unit>%|percent|million|billion|thousand)",
    re.IGNORECASE,
)

# Pattern 2: number followed by a standalone unit word (e.g. "500 employees")
# Only match if unit is a single content word (not a stopword)
_UNIT_WORD_PATTERN = re.compile(
    r"(?P<number>\$?\d[\d,]*\.?\d*)\s+(?P<unit>[a-zA-Z]{2,})",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "of", "in", "on", "at", "to", "for", "by", "with", "from", "as",
    "an", "a", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "being", "has", "have", "had", "that", "this", "these", "those", "which",
    "who", "whom", "where", "when", "how", "what", "all", "each", "than",
    "its", "it", "not", "no", "if", "so", "up", "out", "about", "into",
    "over", "after", "before", "between", "under", "again", "then", "once",
    "here", "there", "why", "both", "few", "more", "most", "other", "some",
    "such", "only", "own", "same", "just", "also", "very", "now", "well",
    "new", "first", "last", "long", "great", "little", "right", "high",
    "old", "different", "big", "large", "next", "early", "small", "local",
}


def _extract_number_claims(text: str) -> list[tuple[str, str, str]]:
    """Return (unit_key, number_str, context_snippet) tuples found in text."""
    claims = []
    seen = set()

    for pat in [_QUANTIFIED_PATTERN, _UNIT_WORD_PATTERN]:
        for match in pat.finditer(text):
            number_str = match.group("number")
            unit = match.group("unit").lower().strip()

            if unit == "%":
                unit = "percent"

            if unit in _STOPWORDS or len(unit) < 2:
                continue

            dedup_key = (unit, number_str)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 30)
            context = text[start:end].strip()
            claims.append((unit, number_str, context))

    return claims


def _numbers_differ(a: str, b: str) -> bool:
    def to_float(s: str) -> float | None:
        cleaned = re.sub(r"[^\d.]", "", s)
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    fa, fb = to_float(a), to_float(b)
    if fa is None or fb is None:
        return a.strip() != b.strip()
    if fa == 0:
        return fb != 0
    return abs(fa - fb) / max(abs(fa), abs(fb)) > 0.02  # >2% difference counts as a conflict


def number_claims_disagree(text_a: str, text_b: str) -> bool:
    """True if two texts make a conflicting claim about the same unit.

    Used by the deduplicator to avoid folding two results that look alike on
    the surface (e.g. identical titles) but disagree numerically — folding
    them together would hide a real conflict from conflict detection.
    """
    claims_a = {unit: number for unit, number, _ in _extract_number_claims(text_a)}
    claims_b = {unit: number for unit, number, _ in _extract_number_claims(text_b)}
    for unit, number_a in claims_a.items():
        number_b = claims_b.get(unit)
        if number_b is not None and _numbers_differ(number_a, number_b):
            return True
    return False


def detect_conflicts(evidence_list: list[Evidence]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for ev_a, ev_b in combinations(evidence_list, 2):
        if ev_a.domain == ev_b.domain:
            continue  # same source, not an independent conflict

        claims_a = _extract_number_claims(ev_a.passage)
        claims_b = _extract_number_claims(ev_b.passage)

        for unit_a, number_a, context_a in claims_a:
            for unit_b, number_b, context_b in claims_b:
                if unit_a != unit_b:
                    continue
                if not _numbers_differ(number_a, number_b):
                    continue
                _a, _b = sorted((ev_a.evidence_id, ev_b.evidence_id))
                pair_key: tuple[str, str] = (_a, _b)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                conflicts.append(
                    Conflict(
                        topic=unit_a,
                        position_a=context_a,
                        position_a_sources=[ev_a.evidence_id],
                        position_b=context_b,
                        position_b_sources=[ev_b.evidence_id],
                        possible_explanation=None,
                    )
                )

    return conflicts
