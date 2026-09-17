"""Source ranking: explicit, documented, configurable heuristics.

We deliberately do NOT claim these weights are scientifically optimal (see
README "Source Ranking"). Three signals are combined:

  relevance_score  — token overlap between the query and the result's
                      title + snippet (cheap, transparent, no external
                      dependency). Range [0, 1].
  authority_score  — domain-based heuristic. Query-dependent: if the query
                      looks like a documentation/technical-reference
                      question, official docs/reference domains are boosted;
                      if the query looks like an opinion/experience
                      question, community sources (forums, Q&A sites) are
                      boosted instead of penalized. Range [0, 1].
  freshness_score  — based on published_date if available, else neutral
                      (0.5) since most search snippets omit a reliable date.
                      Range [0, 1].

final_score = 0.5 * relevance + 0.3 * authority + 0.2 * freshness

These weights are constants at the top of this module specifically so they
are easy to find, justify, and change.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List

from app.models.search import SearchResult

RELEVANCE_WEIGHT = 0.5
AUTHORITY_WEIGHT = 0.3
FRESHNESS_WEIGHT = 0.2

_HIGH_AUTHORITY_DOMAIN_SUFFIXES = (
    ".gov",
    ".edu",
    "docs.python.org",
    "developer.mozilla.org",
    "wikipedia.org",
)
_OFFICIAL_DOC_HINTS = ("docs.", "developer.", "api.")

_COMMUNITY_DOMAINS = {
    "stackoverflow.com",
    "reddit.com",
    "news.ycombinator.com",
    "dev.to",
    "medium.com",
}

_DOC_QUESTION_PATTERN = re.compile(
    r"\b(documentation|api reference|syntax|how to use|official|specification|spec)\b", re.IGNORECASE
)
_EXPERIENCE_QUESTION_PATTERN = re.compile(
    r"\b(experience|opinions?|community|discussion|people think|reviews?|worth it)\b", re.IGNORECASE
)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _relevance_score(query: str, result: SearchResult) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    content_tokens = _tokenize(result.title + " " + result.snippet)
    overlap = query_tokens & content_tokens
    return len(overlap) / len(query_tokens)


def _authority_score(query: str, result: SearchResult) -> float:
    domain = result.domain
    is_doc_question = bool(_DOC_QUESTION_PATTERN.search(query))
    is_experience_question = bool(_EXPERIENCE_QUESTION_PATTERN.search(query))

    score = 0.5  # neutral baseline

    if any(domain.endswith(suffix) or suffix in domain for suffix in _HIGH_AUTHORITY_DOMAIN_SUFFIXES):
        score = 0.9
    elif any(hint in domain for hint in _OFFICIAL_DOC_HINTS):
        score = 0.8

    if domain in _COMMUNITY_DOMAINS:
        score = 0.75 if is_experience_question else 0.45

    if is_doc_question and domain in _COMMUNITY_DOMAINS:
        score = min(score, 0.4)  # community sources rank lower for pure doc questions

    return max(0.0, min(1.0, score))


def _freshness_score(result: SearchResult) -> float:
    if not result.published_date:
        return 0.5  # unknown: neutral, not penalized
    try:
        published = datetime.fromisoformat(result.published_date.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - published).days
    except (ValueError, TypeError):
        return 0.5

    if age_days < 0:
        return 0.5
    if age_days <= 30:
        return 1.0
    if age_days <= 365:
        return 0.7
    if age_days <= 365 * 3:
        return 0.4
    return 0.2


def rank_results(query: str, results: List[SearchResult]) -> List[SearchResult]:
    """Score and sort results in place (descending final_score). Returns the same list, sorted."""
    for result in results:
        relevance = _relevance_score(query, result)
        authority = _authority_score(query, result)
        freshness = _freshness_score(result)
        result.relevance_score = round(relevance, 4)
        result.authority_score = round(authority, 4)
        result.freshness_score = round(freshness, 4)
        result.final_score = round(
            RELEVANCE_WEIGHT * relevance + AUTHORITY_WEIGHT * authority + FRESHNESS_WEIGHT * freshness,
            4,
        )
    results.sort(key=lambda r: r.final_score, reverse=True)
    return results
