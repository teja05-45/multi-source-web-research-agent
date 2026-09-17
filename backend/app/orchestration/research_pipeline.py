"""End-to-end research pipeline: the controlled, observable workflow that
wires every stage together in a fixed order. This is intentionally NOT an
autonomous agent loop — every stage runs exactly once per request (per the
brief's instruction to prefer a controlled workflow over uncontrolled
agents), which keeps behavior predictable, debuggable, and cheap.

Stage order:
  plan -> retrieve (parallel, multi-provider) -> normalize -> deduplicate ->
  rank -> fetch top-N -> build evidence -> detect conflicts -> synthesize ->
  validate citations -> assemble uncertainties -> build final report
"""
from __future__ import annotations

import logging
import re
import time
import uuid

from app.config import Settings
from app.models.claims import Uncertainty
from app.models.query import ResearchRequest
from app.models.report import ProviderOutcome, ResearchReport, ResearchTrace, SourceSummary, TraceResolution
from app.observability.logging import set_request_id
from app.observability.metrics import metrics
from app.planning.planner import plan_research
from app.processing.deduplicator import deduplicate_results
from app.processing.normalizer import normalize_results
from app.processing.ranker import rank_results
from app.providers.base import SearchProvider
from app.question_resolution.models import QuestionResolution
from app.question_resolution.resolver import replace_pronouns
from app.reliability.circuit_breaker import CircuitBreakerRegistry
from app.retrieval.fetcher import fetch_contents
from app.retrieval.orchestrator import run_retrieval
from app.synthesis.llm_client import LLMClient
from app.synthesis.synthesizer import synthesize
from app.verification.citation_validator import validate_claims
from app.verification.conflict_detector import detect_conflicts
from app.verification.verifier import build_evidence

logger = logging.getLogger("research_agent.orchestration")


class ResearchPipeline:
    def __init__(
        self,
        settings: Settings,
        providers: list[SearchProvider],
        llm_client: LLMClient,
        breaker_registry: CircuitBreakerRegistry,
    ) -> None:
        self._settings = settings
        self._providers = providers
        self._llm_client = llm_client
        self._breaker_registry = breaker_registry

    async def run(
        self,
        request: ResearchRequest,
        *,
        resolution: QuestionResolution | None = None,
    ) -> ResearchReport:
        request_id = str(uuid.uuid4())
        set_request_id(request_id)
        start = time.monotonic()

        # Use the resolved question from context resolution if available
        effective_question = resolution.resolved_question if resolution else request.question
        logger.info(
            "research_request_started",
            extra={
                "question": request.question,
                "effective_question": effective_question,
                "resolved_from_context": resolution is not None,
                "resolution_topic": resolution.topic if resolution else None,
                "resolution_intent": resolution.intent.value if resolution else None,
            },
        )

        active_providers = self._select_providers(request.providers)

        # --- Plan ------------------------------------------------------
        effective_max_subqueries = 2 if request.depth == "quick" else self._settings.max_subqueries
        plan = await plan_research(effective_question, self._llm_client, effective_max_subqueries)
        queries = [effective_question] + [q for q in plan.subquestions if q != effective_question]
        # The subject must survive into every query so follow-up research never
        # silently drifts to a different topic.
        queries = self._enforce_subject(queries, resolution)

        stage_timings: dict[str, float] = {}
        last_stage_time = start

        def _mark_stage(label: str) -> None:
            nonlocal last_stage_time
            now = time.monotonic()
            stage_timings[label] = round((now - last_stage_time) * 1000, 1)
            last_stage_time = now

        _mark_stage("planning")
        logger.info(
            "planning_complete",
            extra={"subquery_count": len(plan.subquestions), "used_fallback": plan.used_fallback},
        )

        # --- Retrieve ----------------------------------------------------
        retrieval_outcome = await run_retrieval(
            queries=queries,
            providers=active_providers,
            max_results_per_provider=self._settings.max_results_per_provider,
            max_concurrency=self._settings.retrieval_concurrency,
            max_retries=self._settings.provider_max_retries,
            backoff_base=self._settings.provider_backoff_base_seconds,
            breaker_registry=self._breaker_registry,
        )
        providers_succeeded = sum(1 for o in retrieval_outcome.provider_outcomes if o.succeeded)
        metrics.increment("research.providers_attempted", len(retrieval_outcome.provider_outcomes))
        metrics.increment("research.providers_succeeded", providers_succeeded)
        _mark_stage("retrieval")

        uncertainties: list[Uncertainty] = []
        degraded = False
        for outcome in retrieval_outcome.provider_outcomes:
            if not outcome.succeeded:
                degraded = True
                uncertainties.append(
                    Uncertainty(
                        description=f"Provider '{outcome.name}' failed: {outcome.error}",
                        reason="provider_failure",
                    )
                )

        if active_providers and providers_succeeded == 0:
            logger.error("all_providers_failed", extra={"question": effective_question})
            return self._insufficient_evidence_report(
                request, request_id, plan_subqueries=len(plan.subquestions),
                provider_outcomes=retrieval_outcome.provider_outcomes, start=start,
                reason="All configured search providers failed for this request.",
                resolution=resolution,
            )

        # --- Normalize + Dedupe + Rank ------------------------------------
        normalized = normalize_results(retrieval_outcome.raw_results)
        deduped, duplicates_removed = deduplicate_results(normalized)
        ranked = rank_results(effective_question, deduped)
        _mark_stage("normalization_and_ranking")

        if not ranked:
            uncertainties.append(
                Uncertainty(description="No search results were returned for this question.", reason="no_sources_found")
            )
            return self._insufficient_evidence_report(
                request, request_id, plan_subqueries=len(plan.subquestions),
                provider_outcomes=retrieval_outcome.provider_outcomes, start=start,
                reason="No sources were found for this question.", degraded=degraded,
                resolution=resolution,
            )

        # --- Fetch top-N ---------------------------------------------------
        effective_max_fetch = min(
            request.max_sources,
            5 if request.depth == "quick" else self._settings.max_sources_to_fetch,
        )
        to_fetch = ranked[:effective_max_fetch]
        fetched_by_id = await fetch_contents(to_fetch, self._settings, self._settings.fetch_concurrency)
        sources_fetched = sum(1 for f in fetched_by_id.values() if f.fetched)
        _mark_stage("fetching")

        # --- Evidence + Conflicts -------------------------------------------
        evidence_list = build_evidence(to_fetch, fetched_by_id, query=effective_question)
        conflicts = detect_conflicts(evidence_list)
        if conflicts:
            uncertainties.append(
                Uncertainty(
                    description=f"{len(conflicts)} conflicting piece(s) of evidence were detected.",
                    reason="conflicting_evidence",
                )
            )

        # Topic alignment gate on evidence: if the resolved subject is almost
        # never present in the fetched passages, the retrieval likely drifted
        # off-topic and we must say so rather than synthesize confidently.
        topic_coverage = self._evidence_topic_coverage(evidence_list, resolution)
        evidence_topic_mismatch = (
            resolution is not None
            and bool(resolution.topic)
            and bool(evidence_list)
            and topic_coverage < 0.34
        )
        if evidence_topic_mismatch:
            uncertainties.append(
                Uncertainty(
                    description=(
                        f"Most retrieved evidence does not mention the active topic "
                        f"'{resolution.topic}' (coverage {topic_coverage:.0%}). The answer below "
                        "may reflect off-topic content."
                    ),
                    reason="evidence_topic_mismatch",
                )
            )

        _mark_stage("evidence_and_conflicts")

        # --- Synthesize + Validate --------------------------------------
        answer, raw_claims = await synthesize(
            effective_question,
            evidence_list,
            self._llm_client,
            self._settings.llm_max_output_tokens,
            resolution_context=self._resolution_context(resolution),
        )
        evidence_by_id = {e.evidence_id: e for e in evidence_list}
        verified_claims, unsupported_removed = validate_claims(raw_claims, evidence_by_id, conflicts)
        _mark_stage("synthesis_and_validation")

        total_claims = len(verified_claims)
        citation_coverage = (
            sum(1 for c in verified_claims if c.citations) / total_claims if total_claims else 0.0
        )

        if not raw_claims and evidence_list:
            uncertainties.append(
                Uncertainty(
                    description="The synthesis stage produced no verifiable claims from the available evidence.",
                    reason="unverified_claim",
                )
            )

        # --- Assemble sources ------------------------------------------------
        sources = [
            SourceSummary(
                source_id=r.result_id,
                title=r.title,
                url=r.url,
                domain=r.domain,
                providers=r.providers,
                duplicate_count=r.duplicate_count,
                final_score=r.final_score,
                fetched=bool(fetched_by_id.get(r.result_id) and fetched_by_id[r.result_id].fetched),
            )
            for r in ranked
        ]

        total_latency_ms = (time.monotonic() - start) * 1000
        trace = ResearchTrace(
            request_id=request_id,
            subqueries=len(plan.subquestions),
            providers_attempted=len(retrieval_outcome.provider_outcomes),
            providers_succeeded=providers_succeeded,
            provider_outcomes=retrieval_outcome.provider_outcomes,
            results_retrieved=len(normalized),
            duplicates_removed=duplicates_removed,
            sources_fetched=sources_fetched,
            evidence_items=len(evidence_list),
            conflicts_detected=len(conflicts),
            unsupported_claims_removed=unsupported_removed,
            citation_coverage=round(citation_coverage, 4),
            stage_timings_ms=stage_timings,
            total_latency_ms=round(total_latency_ms, 1),
            resolution=self._trace_resolution(resolution),
        )

        partial = (
            degraded
            or bool(conflicts)
            or unsupported_removed > 0
            or evidence_topic_mismatch
            or (not raw_claims and bool(evidence_list))
        )

        logger.info(
            "research_request_completed",
            extra={
                "request_id": request_id,
                "total_latency_ms": trace.total_latency_ms,
                "citation_coverage": trace.citation_coverage,
                "degraded": degraded,
                "status": "partial" if partial else "completed",
            },
        )
        metrics.observe("research.total_latency_ms", total_latency_ms)

        return ResearchReport(
            request_id=request_id,
            question=request.question,
            answer=answer,
            key_claims=verified_claims,
            sources=sources,
            conflicts=conflicts,
            uncertainties=uncertainties,
            research_trace=trace,
            degraded=degraded,
            status="partial" if partial else "completed",
        )

    def _select_providers(self, requested: list[str] | None) -> list[SearchProvider]:
        if not requested:
            return self._providers
        requested_set = set(requested)
        return [p for p in self._providers if p.name in requested_set]

    @staticmethod
    def _subject_terms(resolution: QuestionResolution | None) -> list[str]:
        """Terms that must be present in every research query."""
        if resolution is None:
            return []
        terms: list[str] = []
        if resolution.topic:
            terms.append(str(resolution.topic).strip())
        for entity in resolution.referenced_entities:
            entity = str(entity).strip()
            if entity and entity.lower() not in {t.lower() for t in terms}:
                terms.append(entity)
        return terms

    @classmethod
    def _enforce_subject(
        cls, queries: list[str], resolution: QuestionResolution | None
    ) -> list[str]:
        """Resolve stray pronouns and prefix the subject so no query drifts."""
        if resolution is None:
            return queries
        terms = cls._subject_terms(resolution)
        if not terms:
            return queries
        topic = terms[0]
        enforced: list[str] = []
        for query in queries:
            # Pronoun references in generated subqueries point at the topic.
            if any(p in query.lower() for p in (" it ", " its ", " its'", " they ", " them ", " their ", " he ", " his ", " she ", " her ", " this ", " that ")):
                query = replace_pronouns(query, topic)
            lowered = query.lower()
            if not any(re.search(rf"\b{re.escape(t)}\b", lowered) for t in terms):
                query = f"{topic} {query}".strip()
            enforced.append(query)
        return enforced

    @staticmethod
    def _trace_resolution(resolution: QuestionResolution | None) -> TraceResolution | None:
        if resolution is None:
            return None
        return TraceResolution(
            raw_question=resolution.raw_question,
            resolved_question=resolution.resolved_question,
            topic=resolution.topic,
            is_follow_up=resolution.is_follow_up,
            intent=resolution.intent.value if resolution.intent else "new_independent",
            referenced_entities=list(resolution.referenced_entities),
            confidence=resolution.confidence,
            needs_clarification=resolution.needs_clarification,
            method=resolution.method,
        )

    @staticmethod
    def _resolution_context(resolution: QuestionResolution | None) -> str | None:
        if resolution is None or not resolution.is_follow_up:
            return None
        lines = [
            "The user asked a follow-up question that was resolved against the "
            "active conversation topic.",
            f"Original question: {resolution.raw_question}",
            f"Resolved question: {resolution.resolved_question}",
        ]
        if resolution.topic:
            lines.append(f"Active topic: {resolution.topic}")
        return "\n".join(lines)

    @staticmethod
    def _evidence_topic_coverage(
        evidence_list, resolution: QuestionResolution | None
    ) -> float:
        """Fraction of evidence whose title/passage mentions the resolved topic."""
        if resolution is None or not resolution.topic or not evidence_list:
            return 1.0
        pattern = re.compile(rf"\b{re.escape(str(resolution.topic))}\b", re.IGNORECASE)
        covered = sum(1 for e in evidence_list if pattern.search(e.title or "") or pattern.search(e.passage or ""))
        return covered / len(evidence_list)

    def _insufficient_evidence_report(
        self,
        request: ResearchRequest,
        request_id: str,
        *,
        plan_subqueries: int,
        provider_outcomes: list[ProviderOutcome],
        start: float,
        reason: str,
        degraded: bool = True,
        stage_timings: dict[str, float] | None = None,
        resolution: QuestionResolution | None = None,
    ) -> ResearchReport:
        total_latency_ms = (time.monotonic() - start) * 1000
        trace = ResearchTrace(
            request_id=request_id,
            subqueries=plan_subqueries,
            providers_attempted=len(provider_outcomes),
            providers_succeeded=sum(1 for o in provider_outcomes if o.succeeded),
            provider_outcomes=provider_outcomes,
            results_retrieved=0,
            duplicates_removed=0,
            sources_fetched=0,
            evidence_items=0,
            conflicts_detected=0,
            citation_coverage=0.0,
            stage_timings_ms=stage_timings or {},
            total_latency_ms=round(total_latency_ms, 1),
            resolution=self._trace_resolution(resolution),
        )
        return ResearchReport(
            request_id=request_id,
            question=request.question,
            answer=(
                "I was unable to find sufficient evidence to answer this question reliably. "
                f"{reason} Rather than guessing, I'm reporting this as insufficient evidence."
            ),
            key_claims=[],
            sources=[],
            conflicts=[],
            uncertainties=[Uncertainty(description=reason, reason="insufficient_evidence")],
            research_trace=trace,
            degraded=degraded,
            status="insufficient_evidence",
        )
