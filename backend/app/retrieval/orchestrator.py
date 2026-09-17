"""Parallel multi-provider, multi-subquery retrieval orchestration.

For each subquery (or the original question alone, if the planner produced
no subquestions), every enabled provider is queried concurrently, bounded by
`retrieval_concurrency`. Each provider call is wrapped with retry-with-
backoff and a circuit breaker. A provider failure never fails the whole
request — its outcome is recorded and the pipeline continues with whatever
other providers returned.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.models.errors import ProviderError
from app.models.report import ProviderOutcome
from app.models.search import RawSearchResult
from app.providers.base import SearchProvider
from app.reliability.circuit_breaker import CircuitBreakerRegistry
from app.reliability.retry import retry_with_backoff

logger = logging.getLogger("research_agent.retrieval.orchestrator")


@dataclass
class RetrievalOutcome:
    raw_results: list[RawSearchResult] = field(default_factory=list)
    provider_outcomes: list[ProviderOutcome] = field(default_factory=list)


async def _call_one_provider(
    provider: SearchProvider,
    query: str,
    max_results: int,
    *,
    max_retries: int,
    backoff_base: float,
    breaker_registry: CircuitBreakerRegistry,
) -> tuple[list[RawSearchResult], ProviderOutcome]:
    breaker = breaker_registry.get(provider.name)
    start = time.monotonic()

    if not breaker.allow_request():
        outcome = ProviderOutcome(
            name=provider.name, succeeded=False, error="circuit_open: provider recently failed repeatedly"
        )
        logger.warning("provider_circuit_open", extra={"provider": provider.name})
        return [], outcome

    async def _op() -> list[RawSearchResult]:
        return await provider.search(query, max_results)

    try:
        results, retries = await retry_with_backoff(
            _op,
            max_retries=max_retries,
            base_delay_seconds=backoff_base,
            provider_name=provider.name,
        )
        breaker.record_success()
        latency_ms = (time.monotonic() - start) * 1000
        outcome = ProviderOutcome(
            name=provider.name,
            succeeded=True,
            result_count=len(results),
            latency_ms=round(latency_ms, 1),
            retries=retries,
        )
        logger.info(
            "provider_call_succeeded",
            extra={"provider": provider.name, "result_count": len(results), "latency_ms": outcome.latency_ms},
        )
        return results, outcome
    except ProviderError as exc:
        breaker.record_failure()
        latency_ms = (time.monotonic() - start) * 1000
        outcome = ProviderOutcome(
            name=provider.name,
            succeeded=False,
            error=exc.message,
            latency_ms=round(latency_ms, 1),
        )
        logger.error(
            "provider_call_failed",
            extra={"provider": provider.name, "error": exc.message, "retryable": exc.retryable},
        )
        return [], outcome


async def run_retrieval(
    *,
    queries: list[str],
    providers: list[SearchProvider],
    max_results_per_provider: int,
    max_concurrency: int,
    max_retries: int,
    backoff_base: float,
    breaker_registry: CircuitBreakerRegistry,
) -> RetrievalOutcome:
    """Run every (query, provider) pair with bounded concurrency."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _bounded_call(query: str, provider: SearchProvider):
        async with semaphore:
            return await _call_one_provider(
                provider,
                query,
                max_results_per_provider,
                max_retries=max_retries,
                backoff_base=backoff_base,
                breaker_registry=breaker_registry,
            )

    tasks = [_bounded_call(query, provider) for query in queries for provider in providers]
    task_results = await asyncio.gather(*tasks) if tasks else []

    all_raw: list[RawSearchResult] = []
    outcomes_by_provider: dict[str, ProviderOutcome] = {}
    for raw_results, outcome in task_results:
        all_raw.extend(raw_results)
        existing = outcomes_by_provider.get(outcome.name)
        if existing is None:
            outcomes_by_provider[outcome.name] = outcome
        else:
            # Merge outcomes across multiple subqueries for the same provider.
            existing.result_count += outcome.result_count
            existing.succeeded = existing.succeeded or outcome.succeeded
            if outcome.error and not existing.error:
                existing.error = outcome.error
            existing.retries += outcome.retries

    return RetrievalOutcome(raw_results=all_raw, provider_outcomes=list(outcomes_by_provider.values()))
