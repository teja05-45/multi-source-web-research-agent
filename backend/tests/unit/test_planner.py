import pytest

from app.planning.planner import plan_research
from app.synthesis.llm_client import LLMClient, LLMCallError


class _FakeLLM(LLMClient):
    def __init__(self, response: str = None, raise_error: bool = False):
        self._response = response
        self._raise_error = raise_error

    async def complete(self, *, system_prompt, user_prompt, max_tokens, temperature=0.0):
        if self._raise_error:
            raise LLMCallError("simulated failure", retryable=True)
        return self._response


@pytest.mark.asyncio
async def test_simple_question_skips_llm_call():
    llm = _FakeLLM(response="should not be used")
    plan = await plan_research("What is the capital of France?", llm, max_subqueries=4)
    assert plan.subquestions == []
    assert not plan.used_fallback


@pytest.mark.asyncio
async def test_complex_question_uses_llm_output():
    llm = _FakeLLM(response='{"subquestions": ["What is approach A?", "What is approach B?"]}')
    plan = await plan_research(
        "Compare approach A and approach B and explain the trade-offs in detail", llm, max_subqueries=4
    )
    assert len(plan.subquestions) == 2
    assert not plan.used_fallback


@pytest.mark.asyncio
async def test_malformed_llm_output_falls_back_deterministically():
    llm = _FakeLLM(response="not valid json at all")
    plan = await plan_research(
        "Compare approach A and approach B and explain the trade-offs in detail", llm, max_subqueries=4
    )
    assert plan.subquestions == []
    assert plan.used_fallback


@pytest.mark.asyncio
async def test_llm_failure_falls_back_deterministically():
    llm = _FakeLLM(raise_error=True)
    plan = await plan_research(
        "Compare approach A and approach B and explain the trade-offs in detail", llm, max_subqueries=4
    )
    assert plan.subquestions == []
    assert plan.used_fallback
