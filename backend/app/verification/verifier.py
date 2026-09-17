"""Builds the Evidence list from ranked results (+ fetched content).

For each ranked SearchResult:
  * if fetched content is available, use `extractor.top_passage` over the
    fetched text as the evidence passage (from_fetched_content=True)
  * otherwise fall back to the provider snippet (from_fetched_content=False)

This function does NOT call the LLM. It builds the grounded evidence set
that synthesis is later restricted to. This ordering — evidence before LLM —
is the central hallucination-reduction mechanism in this system.
"""
from __future__ import annotations

from app.models.evidence import Evidence
from app.models.search import FetchedContent, SearchResult
from app.retrieval.extractor import extract_top_passage, top_passage


def build_evidence(
    ranked_results: list[SearchResult],
    fetched_by_id: dict[str, FetchedContent],
    query: str = "",
) -> list[Evidence]:
    evidence_list: list[Evidence] = []
    for idx, result in enumerate(ranked_results):
        fetched = fetched_by_id.get(result.result_id)
        if fetched and fetched.fetched and fetched.text:
            passage = extract_top_passage(fetched.text, query) if query else top_passage(fetched.text)
            from_fetched = True
        else:
            passage = result.snippet or result.title
            from_fetched = False

        if not passage:
            continue

        evidence_list.append(
            Evidence(
                evidence_id=f"E{idx + 1}",
                source_id=result.result_id,
                url=result.url,
                title=result.title,
                domain=result.domain,
                passage=passage,
                relevance_score=result.relevance_score,
                authority_score=result.authority_score,
                freshness_score=result.freshness_score,
                from_fetched_content=from_fetched,
            )
        )
    return evidence_list
