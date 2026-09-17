"""End-to-end pipeline tests using fake providers and a fake LLM client
(no live network / no real credentials required).
"""
import pytest

from app.config import Settings
from app.models.errors import ProviderError
from app.models.query import ResearchRequest
from app.models.search import RawSearchResult
from app.orchestration.research_pipeline import ResearchPipeline
from app.providers.base import SearchProvider
from app.reliability.circuit_breaker import CircuitBreakerRegistry
from app.synthesis.llm_client import LLMClient


class _FakeProvider(SearchProvider):
    def __init__(self, name, results=None, error: ProviderError | None = None):
        self.name = name
        self._results = results or []
        self._error = error

    async def search(self, query, max_results):
        if self._error:
            raise self._error
        return self._results[:max_results]


class _FakeLLM(LLMClient):
    def __init__(self, response: str):
        self._response = response

    async def complete(self, *, system_prompt, user_prompt, max_tokens, temperature=0.0):
        return self._response


def _settings(**overrides) -> Settings:
    base = dict(
        llm_provider="mock",
        tavily_api_key=None,
        max_fetch_content_bytes=300_000,
        fetch_timeout_seconds=5,
        allow_private_network_fetch=False,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_pipeline_with_two_successful_providers_and_agreeing_evidence():
    provider_a = _FakeProvider(
        "duckduckgo",
        results=[RawSearchResult(provider="duckduckgo", title="Acme Corp has 500 employees", url="https://a.com/x", snippet="Acme Corp has 500 employees worldwide.")],
    )
    provider_b = _FakeProvider(
        "tavily",
        results=[RawSearchResult(provider="tavily", title="Acme Corp employee count", url="https://b.com/y", snippet="Acme Corp has 500 employees worldwide.")],
    )
    llm = _FakeLLM(
        '{"answer": "Acme Corp has 500 employees.", '
        '"claims": [{"text": "Acme Corp has 500 employees.", "citations": ["E1"]}]}'
    )
    pipeline = ResearchPipeline(_settings(), [provider_a, provider_b], llm, CircuitBreakerRegistry(3, 30))
    report = await pipeline.run(ResearchRequest(question="How many employees does Acme Corp have?"))

    assert report.research_trace.providers_succeeded == 2
    assert not report.degraded
    assert report.research_trace.results_retrieved == 2
    assert len(report.sources) >= 1
    assert report.key_claims[0].support_status.value == "supported"


@pytest.mark.asyncio
async def test_pipeline_continues_when_one_provider_fails():
    provider_a = _FakeProvider(
        "duckduckgo",
        results=[RawSearchResult(provider="duckduckgo", title="Some result", url="https://a.com/x", snippet="A relevant snippet about the topic.")],
    )
    provider_b = _FakeProvider("tavily", error=ProviderError("boom", provider="tavily", retryable=False))
    llm = _FakeLLM('{"answer": "Partial answer from one provider.", "claims": []}')

    pipeline = ResearchPipeline(_settings(), [provider_a, provider_b], llm, CircuitBreakerRegistry(3, 30))
    report = await pipeline.run(ResearchRequest(question="What is the topic about?"))

    assert report.degraded is True
    assert report.research_trace.providers_succeeded == 1
    assert any(u.reason == "provider_failure" for u in report.uncertainties)


@pytest.mark.asyncio
async def test_pipeline_returns_insufficient_evidence_when_all_providers_fail():
    provider_a = _FakeProvider("duckduckgo", error=ProviderError("boom", provider="duckduckgo", retryable=False))
    provider_b = _FakeProvider("tavily", error=ProviderError("boom", provider="tavily", retryable=False))
    llm = _FakeLLM('{"answer": "should not be reached", "claims": []}')

    pipeline = ResearchPipeline(_settings(), [provider_a, provider_b], llm, CircuitBreakerRegistry(3, 30))
    report = await pipeline.run(ResearchRequest(question="Anything?"))

    assert report.research_trace.providers_succeeded == 0
    assert report.sources == []
    assert report.key_claims == []
    assert "insufficient" in report.answer.lower()


@pytest.mark.asyncio
async def test_pipeline_detects_conflicting_evidence():
    provider_a = _FakeProvider(
        "duckduckgo",
        results=[RawSearchResult(provider="duckduckgo", title="Employee count A", url="https://a.com/x", snippet="The company has 500 employees today.")],
    )
    provider_b = _FakeProvider(
        "tavily",
        results=[RawSearchResult(provider="tavily", title="Employee count B", url="https://b.com/y", snippet="The company has 700 employees today.")],
    )
    llm = _FakeLLM('{"answer": "Sources disagree on employee count.", "claims": []}')

    pipeline = ResearchPipeline(_settings(), [provider_a, provider_b], llm, CircuitBreakerRegistry(3, 30))
    report = await pipeline.run(ResearchRequest(question="How many employees does the company have?"))

    assert report.research_trace.conflicts_detected >= 1
    assert len(report.conflicts) >= 1


@pytest.mark.asyncio
async def test_pipeline_flags_unsupported_claim_rather_than_trusting_llm():
    provider_a = _FakeProvider(
        "duckduckgo",
        results=[RawSearchResult(provider="duckduckgo", title="Weather report", url="https://a.com/x", snippet="It will be sunny today with mild temperatures.")],
    )
    # LLM hallucinates a completely unrelated, uncited claim.
    llm = _FakeLLM(
        '{"answer": "The company revenue grew 40 percent.", '
        '"claims": [{"text": "The company revenue grew 40 percent.", "citations": ["E1"]}]}'
    )
    pipeline = ResearchPipeline(_settings(), [provider_a], llm, CircuitBreakerRegistry(3, 30))
    report = await pipeline.run(ResearchRequest(question="What is the weather today?"))

    assert report.key_claims[0].support_status.value == "insufficient_evidence"
    assert report.research_trace.unsupported_claims_removed == 1


@pytest.mark.asyncio
async def test_pipeline_handles_malformed_llm_synthesis_output():
    provider_a = _FakeProvider(
        "duckduckgo",
        results=[RawSearchResult(provider="duckduckgo", title="Some result", url="https://a.com/x", snippet="Relevant snippet text.")],
    )
    llm = _FakeLLM("this is not json")
    pipeline = ResearchPipeline(_settings(), [provider_a], llm, CircuitBreakerRegistry(3, 30))
    report = await pipeline.run(ResearchRequest(question="What is this about?"))

    assert report.key_claims == []
    assert "unparseable" in report.answer.lower() or "could not" in report.answer.lower()
