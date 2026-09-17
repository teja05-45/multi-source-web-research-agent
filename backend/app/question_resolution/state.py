"""Build a compact, reusable conversation state from stored history.

Memory ≠ evidence: this state exists only to understand what the user means.
It is never injected into synthesis as a factual source.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.question_resolution.models import ConversationState

logger = logging.getLogger("research_agent.question_resolution.state")

_CAP_TOKEN = r"[A-Z][A-Za-z0-9]*"  # "JavaScript", "OpenAI", "AWS", "iPhone"
_ENTITY_PATTERNS = [
    re.compile(rf"\b{_CAP_TOKEN}(?:\s+{_CAP_TOKEN}){{0,2}}\b"),  # 1-3 token names
]

# Words that are capitalized in natural questions but are NOT entities.
_FUNCTION_WORDS = frozenset({
    "what", "why", "how", "when", "where", "which", "who", "whose", "whom",
    "does", "do", "did", "is", "are", "was", "were", "has", "have", "had",
    "will", "would", "could", "should", "can", "may", "might", "must",
    "compare", "comparison", "tell", "explain", "describe", "list", "show",
    "define", "give", "discuss", "whether", "shouldn't", "isn't", "aren't",
    "didn't", "doesn't", "don't", "can't", "wouldn't", "couldn't",
    "now", "let", "let's", "well", "so", "then", "next", "also", "and",
    "actually", "maybe", "ok", "okay", "today", "talk", "about", "with",
})


def extract_entities(text: str) -> list[str]:
    """Extract explicit capitalized entities in order of appearance.

    Function words (question words, auxiliaries, particles) are stripped from
    candidates so "Is AWS different from Azure?" yields ``["AWS", "Azure"]``
    and "What is JavaScript?" yields ``["JavaScript"]`` — never ``["What"]``
    or a merged ``["Is AWS"]``.
    """
    if not text:
        return []
    seen: list[str] = []
    for pattern in _ENTITY_PATTERNS:
        for match in pattern.findall(text):
            tokens = [t for t in match.strip().split() if t.lower() not in _FUNCTION_WORDS]
            if not tokens:
                continue
            name = " ".join(tokens)
            if (
                len(name) > 1
                and name.lower() not in {w.lower() for w in seen}
            ):
                seen.append(name)
    return seen


def _parse_report_content(content: str) -> dict[str, Any] | None:
    """Best-effort parse of a persisted assistant message (a JSON report)."""
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _answer_summary(content: str) -> str:
    report = _parse_report_content(content)
    if report:
        answer = report.get("answer")
        if answer:
            text = str(answer).strip()
            return text[:600] if len(text) > 600 else text
        topic = report.get("research_trace", {}).get("resolution", {}).get("topic")
        if topic:
            return f"Previously discussed {topic}."
    return content[:600]


def build_conversation_state(
    messages: list[dict[str, Any]],
    research_records: list[dict[str, Any]] | None = None,
    current_question: str | None = None,
) -> ConversationState:
    """Reconstruct a ConversationState from stored messages and research
    records. The current question is excluded so it is never treated as
    "previous" context.
    """
    state = ConversationState()

    # Research records carry explicit resolution metadata (most recent first).
    records = list(research_records or [])
    recent_topics: list[str] = []
    for record in records:
        status = (record.get("status") or "").lower()
        if status not in ("completed", "failed"):
            continue
        payload = record.get("request_payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}
        topic = payload.get("topic")
        resolved = payload.get("resolved_question")
        if topic and str(topic).strip().lower() not in {t.lower() for t in recent_topics}:
            recent_topics.append(str(topic).strip())
        if not state.previous_question and resolved:
            state.previous_question = str(resolved)
    state.recent_research_topics = recent_topics

    # Walk messages chronologically (backwards) to find the previous
    # question / answer and derive the active topic. We walk the full
    # history so the topic can be recovered even when the immediate
    # previous answer carries no explicit subject.
    previous_question: str | None = None
    previous_answer: str | None = None
    resolution_topics: list[str] = []
    body_entities: list[str] = []

    for message in reversed(messages):
        role = message.get("role")
        content = message.get("content") or ""
        if current_question and content.strip() == current_question.strip() and role == "user":
            continue  # this is the question we are resolving right now

        if role == "user":
            if previous_question is None:
                previous_question = content[:500]
            continue

        if role == "assistant":
            if previous_answer is None:
                previous_answer = _answer_summary(content)
            report = _parse_report_content(content)
            resolved = (report or {}).get("research_trace", {}).get("resolution", {})
            topic = resolved.get("topic")
            if topic and str(topic).strip().lower() not in {t.lower() for t in resolution_topics}:
                resolution_topics.append(str(topic).strip())
            for entity in extract_entities(content):
                if entity.lower() not in {e.lower() for e in body_entities}:
                    body_entities.append(entity)

    state.previous_question = previous_question
    state.previous_answer_summary = previous_answer

    # Order candidates: explicit resolution metadata first (most recent),
    # then entities in the previous question, then answer-body entities.
    prior_question_entities: list[str] = []
    if previous_question:
        for entity in extract_entities(previous_question):
            if entity.lower() not in {e.lower() for e in prior_question_entities}:
                prior_question_entities.append(entity)

    candidates: list[str] = []
    for entity in resolution_topics + prior_question_entities + body_entities:
        if entity.lower() not in {c.lower() for c in candidates}:
            candidates.append(entity)

    state.active_entities = candidates

    active_topic = candidates[0] if candidates else (recent_topics[0] if recent_topics else None)
    state.active_topic = active_topic

    return state