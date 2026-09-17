"""Lightweight research planner.

Deliberately NOT an autonomous agent loop. This is a single LLM call (or, for
simple/short questions, a skipped call entirely) that asks the model to
decompose a question into a small number of independently-searchable
subquestions. Output is validated with Pydantic; if the LLM is unavailable,
returns malformed output, or the question is judged too simple to need
decomposition, a deterministic fallback is used instead.
"""
from __future__ import annotations

import json
import logging
import re

from app.models.query import ResearchPlan
from app.synthesis.llm_client import LLMClient, LLMCallError

logger = logging.getLogger("research_agent.planning")

_PLANNER_SYSTEM_PROMPT = """You are a research planning assistant. Given a research \
question, decide whether it benefits from being broken into independent \
sub-questions that can be searched separately.

Rules:
- If the question is simple/factual and decomposition would not help, return \
an empty subquestions list.
- Otherwise return 2 to 4 concise, independently-searchable sub-questions.
- Do not answer the question. Only produce sub-questions.
- Respond with ONLY a JSON object of the form:
{"subquestions": ["...", "..."]}
No prose, no markdown fences, no explanation."""

# A question is treated as "simple" (skip the LLM planning call entirely to
# save cost/latency) if it is short and does not contain comparison/
# multi-part language.
_COMPLEXITY_SIGNAL_PATTERN = re.compile(
    r"\b(compare|versus|vs\.?|trade-?offs?|pros and cons|difference between|"
    r"and how|impact of|relationship between|history of|evolution of)\b",
    re.IGNORECASE,
)


def _looks_simple(question: str) -> bool:
    word_count = len(question.split())
    return word_count <= 12 and not _COMPLEXITY_SIGNAL_PATTERN.search(question)


def _deterministic_fallback(question: str) -> ResearchPlan:
    return ResearchPlan(original_question=question, subquestions=[], used_fallback=True)


async def plan_research(question: str, llm_client: LLMClient, max_subqueries: int) -> ResearchPlan:
    """Produce a ResearchPlan. Never raises: falls back to a plan with no
    subquestions (i.e. search the original question only) on any failure.
    """
    if _looks_simple(question):
        logger.info("planner_skipped_simple_question", extra={"question": question})
        return ResearchPlan(original_question=question, subquestions=[])

    try:
        raw = await llm_client.complete(
            system_prompt=_PLANNER_SYSTEM_PROMPT,
            user_prompt=question,
            max_tokens=300,
            temperature=0.0,
        )
    except LLMCallError as exc:
        logger.warning("planner_llm_call_failed", extra={"error": str(exc)})
        return _deterministic_fallback(question)

    cleaned = raw.strip()
    cleaned = re.sub(r"^```(json)?|```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(cleaned)
        subquestions = parsed.get("subquestions", [])
        if not isinstance(subquestions, list):
            raise ValueError("subquestions is not a list")
        subquestions = [str(s) for s in subquestions][:max_subqueries]
        plan = ResearchPlan(original_question=question, subquestions=subquestions)
        logger.info("planner_succeeded", extra={"subquestion_count": len(plan.subquestions)})
        return plan
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("planner_output_malformed", extra={"error": str(exc), "raw": cleaned[:200]})
        return _deterministic_fallback(question)
