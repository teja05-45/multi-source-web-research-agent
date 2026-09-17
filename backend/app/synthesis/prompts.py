"""Prompt templates for the synthesis stage."""
from __future__ import annotations

from app.models.evidence import Evidence

SYNTHESIS_SYSTEM_PROMPT = """You are a careful research synthesis assistant. You will be given \
a research question and a numbered list of Evidence items, each with an \
evidence ID, a source title/domain, and a passage of text retrieved from \
that source.

STRICT RULES (violating any of these makes your output unusable):
1. Answer ONLY using the supplied evidence. Do not use outside knowledge.
2. Every material factual claim in "claims" MUST cite one or more evidence \
IDs from the supplied list, using the exact IDs given (e.g. "E1", "E3"). \
Never invent an evidence ID.
3. Never invent a source, URL, or citation that was not supplied.
4. If the evidence is insufficient to answer part of the question, say so \
explicitly in the answer rather than filling the gap with assumption.
5. If evidence conflicts, do not silently pick a side; describe the \
disagreement in the answer.
6. Clearly distinguish direct evidence from your own inference, if any \
inference is used.
7. Respond with ONLY a JSON object of this exact shape, no markdown fences, \
no prose outside the JSON:
{
  "answer": "<concise answer, 2-6 sentences>",
  "claims": [
    {"text": "<claim text>", "citations": ["E1", "E2"]}
  ]
}
"""


def format_evidence_block(evidence_list: list[Evidence]) -> str:
    lines = []
    for ev in evidence_list:
        lines.append(f"[{ev.evidence_id}] ({ev.domain}) {ev.title}\n{ev.passage}\n")
    return "\n".join(lines)


def build_user_prompt(
    question: str,
    evidence_list: list[Evidence],
    resolution_context: str | None = None,
) -> str:
    evidence_block = format_evidence_block(evidence_list)
    if resolution_context:
        context_block = f"\n\nConversation context:\n{resolution_context}"
    else:
        context_block = ""
    return f"Research question: {question}{context_block}\n\nEvidence:\n{evidence_block}"
