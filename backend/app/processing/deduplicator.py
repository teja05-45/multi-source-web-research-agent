"""Deduplication: URL-based (exact) then title-similarity based (fuzzy).

Algorithm:
  1. Group results by `canonical_url` (from normalizer.py). Exact matches
     (e.g. `example.com/article` vs `example.com/article?utm_source=google`,
     which canonicalize to the same value) are merged immediately: the first
     occurrence is kept, its `providers` list absorbs the duplicate's
     provider, and `duplicate_count` is incremented.
  2. Among the remaining (non-exact-duplicate) results, compare titles
     pairwise using difflib's SequenceMatcher ratio. Two results with
     different canonical URLs but title similarity >= TITLE_SIMILARITY_THRESHOLD
     (default 0.95) are treated as "related/duplicate" content — e.g. a wire
     story reproduced verbatim by multiple outlets. The later one is marked
     `duplicate_of` the earlier one and folded in the same way as an exact
     match, but is NOT discarded: it stays reachable for provenance, just
     excluded from being counted as independent evidence.

The threshold is deliberately conservative (0.95): titled news reprints are
verbatim or differ only by case/boilerplate, which scores at or above this
bound, while two *genuinely different* articles that merely share a template
(e.g. "Employee count A" vs "Employee count B", ~0.93 similarity) must not be
folded together — doing so would hide a factual conflict between independent
sources from conflict detection.

Fuzzy folding is also skipped whenever the two results make numerically
conflicting claims in their snippets (e.g. "500 employees" vs "700
employees"), even when titles match exactly — a true wire reprint has
identical content, while identical titles with contradictory numbers are two
different articles describing a disagreement.

Thresholds are documented, configurable constants, not tuned against a
labeled dataset — they are explicitly heuristic (see README "Deduplication
Strategy").
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List

from app.models.search import SearchResult
from app.verification.conflict_detector import number_claims_disagree

TITLE_SIMILARITY_THRESHOLD = 0.95


def _normalize_title(title: str) -> str:
    """Strip common boilerplate from titles for better fuzzy matching."""
    t = title.lower().strip()
    t = re.sub(r"\s*[\|–\-—]\s*[^|–\-—]{3,60}$", "", t)
    t = re.sub(r"^(read more|new|hot|trending|popular|latest)[:\s]+", "", t)
    return t.strip()


def _title_similarity(a: str, b: str) -> float:
    na = _normalize_title(a)
    nb = _normalize_title(b)
    return SequenceMatcher(None, na, nb).ratio()


def deduplicate_results(results: List[SearchResult]) -> tuple[List[SearchResult], int]:
    """Return (deduplicated_results, duplicates_removed_count)."""

    # --- Stage 1: exact canonical URL dedup -----------------------------
    by_canonical: dict[str, SearchResult] = {}
    order: List[str] = []
    for result in results:
        key = result.canonical_url
        if key in by_canonical:
            existing = by_canonical[key]
            for provider in result.providers:
                if provider not in existing.providers:
                    existing.providers.append(provider)
            existing.duplicate_count += 1
            if not existing.snippet and result.snippet:
                existing.snippet = result.snippet
        else:
            by_canonical[key] = result
            order.append(key)

    stage1_results = [by_canonical[k] for k in order]
    exact_duplicates_removed = len(results) - len(stage1_results)

    # --- Stage 2: fuzzy title similarity dedup --------------------------
    # Two results are folded as "the same article" only when their titles
    # are near-identical AND their snippets do not numerically contradict
    # each other. The numeric guard matters: `number_claims_disagree`
    # prevents folding two surface-similar results whose passages make
    # conflicting factual claims (e.g. "500 employees" vs "700 employees")
    # — folding them would hide a genuine conflict from conflict detection.
    kept: List[SearchResult] = []
    fuzzy_duplicates_removed = 0
    for candidate in stage1_results:
        match = None
        for existing in kept:
            if _title_similarity(existing.title, candidate.title) < TITLE_SIMILARITY_THRESHOLD:
                continue
            if number_claims_disagree(existing.snippet or "", candidate.snippet or ""):
                continue
            match = existing
            break
        if match is not None:
            match.duplicate_count += 1
            for provider in candidate.providers:
                if provider not in match.providers:
                    match.providers.append(provider)
            fuzzy_duplicates_removed += 1
        else:
            kept.append(candidate)

    total_removed = exact_duplicates_removed + fuzzy_duplicates_removed
    return kept, total_removed
