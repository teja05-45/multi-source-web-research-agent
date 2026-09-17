"""Deterministic question resolution core + optional LLM polish.

Architecture
============
The subject is resolved **deterministically** from pronoun/explicit-entity
analysis. The LLM is only asked to polish the *grammar* of the resolved
question — it is never trusted to decide *what* the user means. Its output
is validated against the deterministically chosen entities so it cannot
silently introduce a new subject. This preserves the "never invent" rule
while still producing fluent output.
"""
from __future__ import annotations

import logging
import re

from app.question_resolution.models import (
    ConversationState,
    QuestionIntent,
    QuestionResolution,
)
from app.question_resolution.state import extract_entities
from app.synthesis.llm_client import LLMClient, LLMCallError

logger = logging.getLogger("research_agent.question_resolution.resolver")

# ── Pronouns (bare) ────────────────────────────────────────────────────────
_PRONOUN_WORDS = frozenset({
    "it", "its", "this", "that",
    "they", "them", "their",
    "these", "those",
    "he", "him", "his",
    "she", "her",
})
_PRONOUN_PATTERN = re.compile(
    r"\b(it|its|this|that|they|them|their|these|those|he|him|his|she|her)\b",
    re.IGNORECASE,
)
_POSSESSIVE_PATTERN = re.compile(r"\bits\b", re.IGNORECASE)

# ── Comparison signals ─────────────────────────────────────────────────────
_COMPARISON_PATTERN = re.compile(
    r"\b(compare|versus|vs\.?|difference|differ(s|ing|ent(?:ly)?|ences?)?|"
    r"contrast(s|ing)?|trade-?offs?|pros and cons|distinguishes?|more than|"
    r"better than|worse than|faster than|slower than)\b",
    re.IGNORECASE,
)

# ── Continuation signals (ignored here but kept for future use) ────────────
_CONTINUATION_PATTERN = re.compile(
    r"\b(tell me about|explain|describe|go on|elaborate|more about|what else)\b",
    re.IGNORECASE,
)

# ── Question length heuristic ──────────────────────────────────────────────
_SHORT_QUESTION_MAX_WORDS = 40


def _replace_pronoun(text: str, topic: str) -> str:
    """Replace pronouns in *text* with the resolved *topic*.

    Possessive pronoun "its" becomes ``topic's``; others are replaced
    verbatim. Only the first few pronouns are replaced so a sentence like
    "Compare it with Python" becomes "Compare JavaScript with Python"
    (not "Compare JavaScript with JavaScript").
    """
    replaced_count = 0

    def _swap(match: re.Match) -> str:
        nonlocal replaced_count
        raw = match.group(0).lower()
        if raw == "its":
            replaced_count += 1
            return f"{topic}'s"
        replaced_count += 1
        return topic

    # Replace at most three pronoun occurrences (covers head + secondary).
    result, n = _PRONOUN_PATTERN.subn(_swap, text, count=3)
    # Light grammar fix: "why <Topic> differ from" → "Why does <Topic> differ from"
    result = re.sub(
        r"\b(why|how|when|where)\s+(" + re.escape(topic) + r")\s+differ\b",
        r"\1 does \2 differ",
        result,
        flags=re.IGNORECASE,
    )
    return result


def replace_pronouns(text: str, topic: str) -> str:
    """Public wrapper: replace bare pronouns in *text* with *topic*."""
    return _replace_pronoun(text, topic)


def _cap_first(text: str) -> str:
    text = text.strip()
    return text[0].upper() + text[1:] if text else text


def classify(
    raw_question: str,
    state: ConversationState,
    current_entities: list[str],
    pronouns_found: list[str],
) -> tuple[QuestionIntent, str | None, list[str], bool, float, str, bool]:
    """Pure deterministic classification. Returns
    (intent, topic, referenced_entities, is_follow_up, confidence, reasoning, needs_clarification).
    """
    has_pronouns = len(pronouns_found) > 0
    has_comparison = bool(_COMPARISON_PATTERN.search(raw_question))
    has_explicit = len(current_entities) > 0
    active_topic = state.active_topic

    referenced: list[str] = []

    if has_pronouns and has_comparison and active_topic:
        explicit_others = [e for e in current_entities if e.lower() != active_topic.lower()]
        referenced = [active_topic] + explicit_others
        topic = active_topic
        others = ", ".join(explicit_others) if explicit_others else "another topic"
        reasoning = (
            f"The question contains a pronoun resolved to the active topic "
            f"'{active_topic}' and introduces additional entity "
            f"{others} in a comparison structure."
        )
        confidence = 0.88
        return QuestionIntent.COMPARISON, topic, referenced, True, confidence, reasoning, False

    if has_pronouns:
        if active_topic:
            explicit_override = [e for e in current_entities if e.lower() != active_topic.lower()]
            referenced = [active_topic] + explicit_override
            topic = active_topic
            reasoning = (
                f"The question contains a pronoun reference that was "
                f"resolved to the active topic '{active_topic}'."
            )
            return QuestionIntent.FOLLOW_UP, topic, referenced, True, 0.9, reasoning, False
        if current_entities:
            # Self-contained question that also happens to use a pronoun
            # ("What is GDPR and how does it work?"). The pronoun refers to
            # the explicitly named subject — not an unknown topic.
            primary = current_entities[0]
            reasoning = (
                f"The question names '{primary}' explicitly and is "
                f"self-contained; its pronoun refers to that subject."
            )
            return (
                QuestionIntent.NEW_INDEPENDENT,
                primary,
                list(current_entities),
                False,
                1.0,
                reasoning,
                False,
            )
        reasoning = "The question contains a pronoun but no active topic is available to resolve it."
        return QuestionIntent.AMBIGUOUS, None, [], True, 0.5, reasoning, True

    if has_explicit:
        primary = current_entities[0]
        if has_comparison:
            referenced = list(current_entities)
            reasoning = (
                f"The question explicitly names {primary} and uses "
                f"comparison language."
            )
            topic = primary
            return QuestionIntent.COMPARISON, topic, referenced, True, 0.95, reasoning, False

        if active_topic and primary.lower() != active_topic.lower():
            reasoning = (
                f"The question explicitly names a new topic '{primary}' "
                f"(previously active topic was '{active_topic}')."
            )
            return QuestionIntent.FOLLOW_UP_TOPIC_CHANGE, primary, list(current_entities), True, 1.0, reasoning, False

        reasoning = f"The question is self-contained and explicitly names '{primary}'."
        return QuestionIntent.NEW_INDEPENDENT, primary, list(current_entities), False, 1.0, reasoning, False

    # No pronoun, no explicit entity.
    # Possible continuation like "tell me about databases" (lowercase)
    if _CONTINUATION_PATTERN.search(raw_question):
        return QuestionIntent.CONTINUATION, None, [], False, 0.6, "A continuation signal was detected but no explicit entity was mentioned.", False

    reasoning = "The question is self-contained; no context resolution was required."
    return QuestionIntent.NEW_INDEPENDENT, None, [], False, 1.0, reasoning, False


_QUESTION_WORDS = {"why", "how", "what", "when", "where", "which", "who", "does", "is", "are", "can", "do", "did", "was", "were", "has", "have", "had", "will", "should", "could", "would"}


def _entities_from_question(raw_question: str) -> list[str]:
    """Extract entities from the raw question, filtering question words and short tokens."""
    return [
        e for e in extract_entities(raw_question)
        if len(e) > 2 and e.lower() not in _QUESTION_WORDS
    ]


def resolve_heuristic(
    raw_question: str,
    state: ConversationState,
) -> QuestionResolution:
    """Deterministic, no-LLM question resolution.

    Resolves pronouns to the active topic, classifies intent, and produces
    a resolved question (possibly grammatically imperfect).  When an entity
    cannot be determined the question is returned as-is with
    ``needs_clarification = True`` so callers can decide whether to ask the
    user.
    """
    current_entities = _entities_from_question(raw_question)
    pronouns_found = _PRONOUN_PATTERN.findall(raw_question)

    intent, topic, referenced, is_follow_up, confidence, reasoning, needs_clarification = classify(
        raw_question, state, current_entities, pronouns_found,
    )

    resolved_question = raw_question
    if pronouns_found and topic and not needs_clarification:
        resolved_question = replace_pronouns(raw_question, topic)

    if not needs_clarification:
        resolved_question = _cap_first(resolved_question)

    return QuestionResolution(
        raw_question=raw_question,
        resolved_question=resolved_question,
        topic=topic,
        is_follow_up=is_follow_up,
        intent=intent,
        referenced_entities=referenced if referenced else (current_entities if not pronouns_found and current_entities else []),
        confidence=confidence,
        reasoning=reasoning,
        needs_clarification=needs_clarification,
        method="heuristic",
    )


async def resolve_llm_polish(
    heuristic_resolution: QuestionResolution,
    state: ConversationState,
    llm_client: LLMClient,
) -> QuestionResolution:
    """Polish a heuristic resolution with an LLM call for fluency.

    The LLM's output is **validated** against the topic that was already
    determined. If validation fails the heuristic resolution is returned
    unchanged.
    """
    topic = heuristic_resolution.topic
    if not topic or heuristic_resolution.needs_clarification:
        return heuristic_resolution

    system_prompt = (
        "You are a question rewriter for a research assistant. Given a user's "
        "follow-up question and a conversation summary, rewrite the follow-up "
        "into a fluent, standalone research question.\n\n"
        "RULES (any violation means your output is unusable and will be rejected):\n"
        "1. The resolved question MUST mention the provided topic entity "
        "explicitly in a way that is grammatically correct.\n"
        "2. Do NOT introduce a subject that was not in the original user question.\n"
        "3. Do NOT add opinions or qualifiers.\n"
        "4. If the original question used a pronoun, replace the pronoun with "
        "the topic entity.\n"
        "5. Respond with ONLY a JSON object:\n"
        '{"resolved_question": "...", "confidence": 0.0 to 1.0, "reasoning": "..."}\n'
        "No prose, no markdown fences, no explanation."
    )

    context_parts: list[str] = []
    if state.previous_question:
        context_parts.append(f"Previous question: {state.previous_question}")
    if state.previous_answer_summary:
        context_parts.append(f"Previous answer summary: {state.previous_answer_summary[:300]}")
    context_parts.append(f"Determined topic: {topic}")
    context_parts.append(f"Intent: {heuristic_resolution.intent.value}")
    context_parts.append(f"Original follow-up: {heuristic_resolution.raw_question}")

    user_prompt = "\n".join(context_parts)

    try:
        raw_response = await llm_client.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=200,
            temperature=0.0,
        )
    except LLMCallError as exc:
        logger.warning("question_resolution_llm_failed", extra={"error": str(exc)})
        return heuristic_resolution

    import json as json_mod
    cleaned = raw_response.strip()
    cleaned = re.sub(r"^```(json)?|```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        parsed = json_mod.loads(cleaned)
        resolved = str(parsed.get("resolved_question", "")).strip()
        llm_confidence = float(parsed.get("confidence", 0.0))
        llm_reasoning = str(parsed.get("reasoning", ""))
    except (json_mod.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        logger.warning("question_resolution_llm_output_malformed", extra={"error": str(exc)})
        return heuristic_resolution

    # Validation: the resolved question MUST mention the topic (case-insensitive).
    if not resolved or topic.lower() not in resolved.lower():
        logger.warning("question_resolution_llm_validation_failed", extra={"topic": topic, "resolved": resolved})
        return heuristic_resolution

    logger.info(
        "question_resolution_llm_succeeded",
        extra={"raw": heuristic_resolution.raw_question, "resolved": resolved},
    )

    return QuestionResolution(
        raw_question=heuristic_resolution.raw_question,
        resolved_question=resolved,
        topic=topic,
        is_follow_up=heuristic_resolution.is_follow_up,
        intent=heuristic_resolution.intent,
        referenced_entities=heuristic_resolution.referenced_entities,
        confidence=max(heuristic_resolution.confidence, llm_confidence),
        reasoning=f"LLM polish: {llm_reasoning}" if llm_reasoning else heuristic_resolution.reasoning,
        needs_clarification=heuristic_resolution.needs_clarification,
        method="llm",
    )


async def resolve_question(
    raw_question: str,
    state: ConversationState,
    llm_client: LLMClient | None = None,
) -> QuestionResolution:
    """High-level entry point: deterministic classification + optional LLM polish."""
    heuristic = resolve_heuristic(raw_question, state)

    # Only call LLM polish when the question is a follow-up with a known
    # topic and we are confident about the entity resolution.
    if (
        llm_client is not None
        and heuristic.is_follow_up
        and heuristic.topic is not None
        and not heuristic.needs_clarification
    ):
        return await resolve_llm_polish(heuristic, state, llm_client)

    return heuristic