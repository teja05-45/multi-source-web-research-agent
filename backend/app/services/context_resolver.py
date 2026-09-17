"""Context resolution for follow-up questions.

This module handles resolving follow-up questions using conversation context.
It extracts entities, topics, and scope from previous turns to help form
better research queries.

IMPORTANT: Memory/context helps form better queries. Only freshly retrieved
and verified evidence may support factual claims. This distinction is
enforced architecturally.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from app.models.conversation import Message
from app.repositories.conversation_repo import MessageRepository
from app.synthesis.llm_client import LLMClient, LLMCallError

logger = logging.getLogger("research_agent.context_resolver")


# Patterns for detecting follow-up references
_FOLLOWUP_PATTERNS = [
    r"\b(what about|how about|tell me about|what are the|what is the)\b",
    r"\b(and |also |plus )\b",
    r"\b(their|its|his|her|this|that|these|those)\b",
    r"\b(limitations|risks|benefits|drawbacks|advantages|disadvantages)\b",
    r"\b(compared to|versus|vs\.?)\b",
]

_ENTITY_PATTERNS = [
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",  # Capitalized phrases (proper nouns)
    r"\b([A-Z]{2,}(?:\s+[A-Z]{2,})*)\b",       # Acronyms
]


@dataclass
class ResolvedContext:
    """Resolved context for a follow-up question."""
    original_question: str
    resolved_question: str
    entities: List[str]
    topics: List[str]
    scope: str
    used_fallback: bool = False


class ContextResolver:
    """Resolves follow-up questions using conversation context."""

    def __init__(
        self,
        message_repo: MessageRepository,
        llm_client: LLMClient,
        max_context_messages: int = 5,
    ):
        self._message_repo = message_repo
        self._llm_client = llm_client
        self._max_context_messages = max_context_messages

    async def resolve(self, conversation_id: str, question: str) -> ResolvedContext:
        """Resolve a follow-up question using conversation context.

        Returns a ResolvedContext with the original question, resolved question,
        extracted entities, topics, and scope.
        """
        # Check if this looks like a follow-up question
        if not self._looks_like_followup(question):
            # Simple question - no context resolution needed
            entities, topics = self._extract_entities_and_topics(question)
            return ResolvedContext(
                original_question=question,
                resolved_question=question,
                entities=entities,
                topics=topics,
                scope="general",
            )

        # Get recent conversation context
        recent_messages = await self._message_repo.get_last_n(
            conversation_id, self._max_context_messages
        )

        if not recent_messages:
            # No context available
            entities, topics = self._extract_entities_and_topics(question)
            return ResolvedContext(
                original_question=question,
                resolved_question=question,
                entities=entities,
                topics=topics,
                scope="general",
            )

        # Try LLM-based resolution
        try:
            resolved = await self._resolve_with_llm(question, recent_messages)
            if resolved:
                logger.info(
                    "context_resolved",
                    extra={
                        "conversation_id": conversation_id,
                        "original": question,
                        "resolved": resolved.resolved_question,
                    },
                )
                return resolved
        except Exception as exc:
            logger.warning("context_resolution_failed", extra={"error": str(exc)})

        # Fallback: simple heuristic resolution
        return self._resolve_heuristic(question, recent_messages)

    def _looks_like_followup(self, question: str) -> bool:
        """Check if question appears to be a follow-up."""
        question_lower = question.lower()
        return any(re.search(pattern, question_lower) for pattern in _FOLLOWUP_PATTERNS)

    def _extract_entities_and_topics(self, text: str) -> tuple[List[str], List[str]]:
        """Extract entities and topics from text using simple heuristics."""
        entities = []
        topics = []

        # Extract capitalized phrases as potential entities
        for pattern in _ENTITY_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                match = match.strip()
                if len(match) > 2 and match not in entities:
                    entities.append(match)

        # Extract topics from question words
        topic_keywords = [
            "security", "performance", "cost", "scalability", "reliability",
            "architecture", "implementation", "deployment", "monitoring",
            "limitation", "risk", "benefit", "drawback", "advantage",
            "trade-off", "comparison", "benchmark", "best practice",
        ]
        text_lower = text.lower()
        for keyword in topic_keywords:
            if keyword in text_lower and keyword not in topics:
                topics.append(keyword)

        return entities, topics

    async def _resolve_with_llm(
        self, question: str, recent_messages: List[Message]
    ) -> Optional[ResolvedContext]:
        """Use LLM to resolve the follow-up question."""
        # Build conversation context
        context_parts = []
        for msg in recent_messages:
            role = "User" if msg.role == "user" else "Assistant"
            content = msg.content[:500]  # Truncate long messages
            context_parts.append(f"{role}: {content}")

        conversation_context = "\n".join(context_parts)

        system_prompt = """You are a research context resolver. Given a conversation history and a follow-up question, 
resolve the follow-up into a complete, standalone research question.

Rules:
1. Identify what the follow-up is referring to (entities, topics, scope from previous turns)
2. Produce a complete question that can be researched independently
3. Extract key entities and topics mentioned
4. Determine the scope (technical, business, security, etc.)

Output ONLY a JSON object:
{
  "resolved_question": "...",
  "entities": ["entity1", "entity2"],
  "topics": ["topic1", "topic2"],
  "scope": "technical|business|security|general"
}"""

        user_prompt = f"Conversation history:\n{conversation_context}\n\nFollow-up question: {question}"

        try:
            raw = await self._llm_client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=300,
                temperature=0.0,
            )

            import json
            import re

            cleaned = raw.strip()
            cleaned = re.sub(r"^```(json)?|```$", "", cleaned, flags=re.MULTILINE).strip()

            parsed = json.loads(cleaned)
            resolved_question = parsed.get("resolved_question", question)
            entities = parsed.get("entities", [])
            topics = parsed.get("topics", [])
            scope = parsed.get("scope", "general")

            return ResolvedContext(
                original_question=question,
                resolved_question=resolved_question,
                entities=entities,
                topics=topics,
                scope=scope,
            )
        except (json.JSONDecodeError, KeyError, LLMCallError) as exc:
            logger.warning("llm_context_resolution_failed", extra={"error": str(exc)})
            return None

    def _resolve_heuristic(
        self, question: str, recent_messages: List[Message]
    ) -> ResolvedContext:
        """Heuristic-based fallback resolution."""
        # Extract key terms from recent assistant messages
        entities = []
        topics = []

        for msg in recent_messages:
            if msg.role == "assistant":
                # Try to extract key terms from the answer
                e, t = self._extract_entities_and_topics(msg.content)
                entities.extend(e)
                topics.extend(t)

        # Deduplicate
        entities = list(dict.fromkeys(entities))
        topics = list(dict.fromkeys(topics))

        # Simple resolution: prepend context
        if entities:
            context_prefix = f"{entities[0]}" + (f" and {entities[1]}" if len(entities) > 1 else "")
            resolved = f"{question} (in context of {context_prefix})"
        elif topics:
            resolved = f"{question} (regarding {topics[0]})"
        else:
            resolved = question

        return ResolvedContext(
            original_question=question,
            resolved_question=resolved,
            entities=entities,
            topics=topics,
            scope="general",
            used_fallback=True,
        )