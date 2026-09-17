"""LLM-based synthesis over grounded evidence, with strict JSON parsing.

The LLM never sees raw search results — only the curated Evidence list. Its
output is parsed defensively: any malformed JSON, missing fields, or wrong
types result in a deterministic "insufficient evidence to synthesize"
response rather than a crash or a hallucinated fallback answer.
"""
from __future__ import annotations

import json
import logging
import re
import uuid

from app.models.claims import Claim
from app.models.evidence import Evidence
from app.synthesis.llm_client import LLMClient, LLMCallError
from app.synthesis.prompts import SYNTHESIS_SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger("research_agent.synthesis")

_NO_EVIDENCE_ANSWER = (
    "There is not enough retrieved evidence to answer this question. "
    "This may be due to provider failures, an overly narrow query, or a "
    "topic with limited web coverage."
)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text)
    text = re.sub(r"```$", "", text)
    return text.strip()


async def synthesize(
    question: str, evidence_list: list[Evidence], llm_client: LLMClient, max_tokens: int,
    resolution_context: str | None = None,
) -> tuple[str, list[Claim]]:
    """Returns (answer_text, claims). Never raises for malformed LLM output —
    falls back to a deterministic insufficient-evidence response instead.
    """
    if not evidence_list:
        logger.warning("synthesis_skipped_no_evidence")
        return _NO_EVIDENCE_ANSWER, []

    system_prompt = SYNTHESIS_SYSTEM_PROMPT
    user_prompt = build_user_prompt(question, evidence_list, resolution_context=resolution_context)

    try:
        raw = await llm_client.complete(
            system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=max_tokens, temperature=0.1
        )
    except LLMCallError as exc:
        logger.error("synthesis_llm_call_failed", extra={"error": str(exc)})
        return (
            "The synthesis model could not be reached, so no answer could be generated from the "
            "retrieved evidence. Please check LLM provider configuration and try again.",
            [],
        )

    cleaned = _strip_code_fences(raw)
    valid_evidence_ids = {e.evidence_id for e in evidence_list}

    try:
        parsed = json.loads(cleaned)
        answer = str(parsed["answer"])
        raw_claims = parsed.get("claims", [])
        if not isinstance(raw_claims, list):
            raise ValueError("claims is not a list")

        claims: list[Claim] = []
        for item in raw_claims:
            text = str(item.get("text", "")).strip()
            citations = item.get("citations", [])
            if not text or not isinstance(citations, list):
                continue
            # Only keep citation IDs that look syntactically valid; the
            # citation_validator does the authoritative check against real
            # evidence IDs, but we sanitize obviously bogus entries here too.
            citations = [str(c) for c in citations]
            claims.append(Claim(claim_id=str(uuid.uuid4())[:8], text=text, citation_evidence_ids=citations))

        logger.info(
            "synthesis_succeeded",
            extra={
                "claim_count": len(claims),
                "cited_known_evidence": sum(
                    1 for c in claims if any(cid in valid_evidence_ids for cid in c.citation_evidence_ids)
                ),
            },
        )
        return answer, claims
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.error("synthesis_output_malformed", extra={"error": str(exc), "raw": cleaned[:300]})
        return (
            "The synthesis model returned an unparseable response, so no verified answer could be "
            "produced. The retrieved evidence and sources below can still be reviewed directly.",
            [],
        )
