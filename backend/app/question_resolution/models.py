"""Question-resolution data model.

A *resolved question* is the canonical, self-contained research question that
replaces the user's raw utterance before it reaches the retrieval pipeline.

Key invariant: **the subject is decided deterministically**. The optional LLM
polish pass may rephrase for fluency but must never introduce a new subject —
its output is validated against the deterministically chosen entities. Memory
is used to understand the user; it is never treated as evidence (fresh
retrieval still happens for every answer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class QuestionIntent(str, Enum):
    NEW_INDEPENDENT = "new_independent"
    FOLLOW_UP = "follow_up"
    FOLLOW_UP_TOPIC_CHANGE = "follow_up_topic_change"
    COMPARISON = "comparison"
    CLARIFICATION = "clarification"
    CONTINUATION = "continuation"
    AMBIGUOUS = "ambiguous"


@dataclass
class ConversationState:
    """Compact semantic summary of a conversation (NOT evidence)."""

    previous_question: str | None = None
    previous_answer_summary: str | None = None
    active_topic: str | None = None
    active_entities: list[str] = field(default_factory=list)  # most recent first
    recent_research_topics: list[str] = field(default_factory=list)
    unresolved_references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "previous_question": self.previous_question,
            "previous_answer_summary": self.previous_answer_summary,
            "active_topic": self.active_topic,
            "active_entities": list(self.active_entities),
            "recent_research_topics": list(self.recent_research_topics),
            "unresolved_references": list(self.unresolved_references),
        }


@dataclass
class QuestionResolution:
    """Structured output of the question resolution stage."""

    raw_question: str
    resolved_question: str
    topic: str | None = None
    is_follow_up: bool = False
    intent: QuestionIntent = QuestionIntent.NEW_INDEPENDENT
    referenced_entities: list[str] = field(default_factory=list)
    confidence: float = 1.0
    reasoning: str = "The question is self-contained; no context resolution was required."
    needs_clarification: bool = False
    method: str = "identity"  # "identity" | "heuristic" | "llm" | "ambiguous"

    _PRONOUN_FORMS = {"it", "its", "this", "that", "these", "those", "they", "them", "their", "he", "she", "him", "her"}

    def to_dict(self) -> dict:
        return {
            "raw_question": self.raw_question,
            "resolved_question": self.resolved_question,
            "topic": self.topic,
            "is_follow_up": self.is_follow_up,
            "intent": self.intent.value,
            "referenced_entities": list(self.referenced_entities),
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "method": self.method,
        }