"""Deterministic evaluation harness.

This does NOT make live calls to real search/LLM APIs by default — it runs
the full pipeline against controlled fake providers and a fake LLM so the
evaluation is reproducible and free, and specifically exercises each
benchmark category (duplicate-heavy retrieval, conflicting sources,
provider failure, insufficient evidence, etc).

For each dataset item we report ACTUAL measured properties of the pipeline
output (not a fabricated accuracy number). See docs/EVALUATION_RESULTS.md
for the last recorded run.

Usage:
    cd backend
    python -m tests.evaluation.run_evaluation
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.models.query import ResearchRequest
from app.models.search import RawSearchResult
from app.orchestration.research_pipeline import ResearchPipeline
from app.providers.base import SearchProvider
from app.reliability.circuit_breaker import CircuitBreakerRegistry
from app.synthesis.llm_client import LLMClient
from app.models.errors import ProviderError

DATASET_PATH = Path(__file__).parent / "dataset.json"


class _ScenarioProvider(SearchProvider):
    def __init__(self, name, results=None, error=None):
        self.name = name
        self._results = results or []
        self._error = error

    async def search(self, query, max_results):
        if self._error:
            raise self._error
        return self._results[:max_results]


class _ScenarioLLM(LLMClient):
    async def complete(self, *, system_prompt, user_prompt, max_tokens, temperature=0.0):
        if "sub-question" in system_prompt.lower():
            if "compare" in user_prompt.lower() or "trade-offs" in user_prompt.lower():
                return '{"subquestions": ["What is approach A?", "What is approach B?"]}'
            return '{"subquestions": []}'
        # naive synthesis: cite the first evidence block if present
        if "[E1]" in user_prompt:
            return '{"answer": "Based on the retrieved evidence.", "claims": [{"text": "Based on the retrieved evidence.", "citations": ["E1"]}]}'
        return '{"answer": "No strong evidence was available.", "claims": []}'


def _settings() -> Settings:
    return Settings(llm_provider="mock", tavily_api_key=None)


def _scenario_for(item: dict) -> tuple[list[SearchProvider], LLMClient]:
    category = item["category"]
    llm = _ScenarioLLM()

    if category == "provider_failure":
        good = _ScenarioProvider(
            "duckduckgo",
            results=[RawSearchResult(provider="duckduckgo", title="REST vs GraphQL", url="https://a.com/x", snippet="REST uses fixed endpoints while GraphQL uses a single flexible query endpoint.")],
        )
        bad = _ScenarioProvider("tavily", error=ProviderError("simulated outage", provider="tavily", retryable=True))
        return [good, bad], llm

    if category == "insufficient_evidence":
        empty_a = _ScenarioProvider("duckduckgo", results=[])
        empty_b = _ScenarioProvider("tavily", results=[])
        return [empty_a, empty_b], llm

    if category == "conflicting_sources":
        a = _ScenarioProvider("duckduckgo", results=[RawSearchResult(provider="duckduckgo", title="Employee count", url="https://a.com/x", snippet="The company has 500 employees today.")])
        b = _ScenarioProvider("tavily", results=[RawSearchResult(provider="tavily", title="Employee count", url="https://b.com/y", snippet="The company has 700 employees today.")])
        return [a, b], llm

    if category == "duplicate_heavy":
        a = _ScenarioProvider("duckduckgo", results=[RawSearchResult(provider="duckduckgo", title="Company announces new product today", url="https://a.com/press?utm_source=x", snippet="The company announced a new product today.")])
        b = _ScenarioProvider("tavily", results=[RawSearchResult(provider="tavily", title="Company announces new product today", url="https://a.com/press", snippet="The company announced a new product today.")])
        return [a, b], llm

    # default: simple_factual, multi_step, current_information
    a = _ScenarioProvider("duckduckgo", results=[RawSearchResult(provider="duckduckgo", title="Relevant result", url="https://a.com/x", snippet="A relevant, directly related snippet answering the question.")])
    b = _ScenarioProvider("tavily", results=[RawSearchResult(provider="tavily", title="Second relevant result", url="https://b.com/y", snippet="A second independent relevant snippet.")])
    return [a, b], llm


async def run_all() -> dict:
    dataset = json.loads(DATASET_PATH.read_text())
    results = []

    for item in dataset:
        providers, llm = _scenario_for(item)
        pipeline = ResearchPipeline(_settings(), providers, llm, CircuitBreakerRegistry(3, 30))
        report = await pipeline.run(ResearchRequest(question=item["question"]))

        results.append(
            {
                "id": item["id"],
                "category": item["category"],
                "providers_succeeded": report.research_trace.providers_succeeded,
                "providers_attempted": report.research_trace.providers_attempted,
                "results_retrieved": report.research_trace.results_retrieved,
                "duplicates_removed": report.research_trace.duplicates_removed,
                "sources_returned": len(report.sources),
                "conflicts_detected": report.research_trace.conflicts_detected,
                "degraded": report.degraded,
                "claims_supported": sum(1 for c in report.key_claims if c.support_status.value == "supported"),
                "claims_flagged_insufficient": sum(
                    1 for c in report.key_claims if c.support_status.value == "insufficient_evidence"
                ),
            }
        )

    # Aggregate metrics computed from actual results above (not invented).
    n = len(results)
    retrieval_success = sum(1 for r in results if r["providers_succeeded"] > 0) / n
    graceful_failure_rate = sum(
        1 for r in results if r["providers_succeeded"] == 0 or r["degraded"]
    ) / n if any(r["category"] in ("provider_failure", "insufficient_evidence") for r in results) else None
    duplicate_handling_exercised = any(r["duplicates_removed"] > 0 for r in results)
    conflict_detection_exercised = any(r["conflicts_detected"] > 0 for r in results)

    summary = {
        "items_evaluated": n,
        "retrieval_success_rate": round(retrieval_success, 3),
        "graceful_failure_rate": (
            round(graceful_failure_rate, 3) if graceful_failure_rate is not None else None
        ),
        "duplicate_handling_exercised": duplicate_handling_exercised,
        "conflict_detection_exercised": conflict_detection_exercised,
        "per_item_results": results,
    }
    return summary


if __name__ == "__main__":
    summary = asyncio.run(run_all())
    print(json.dumps(summary, indent=2))
