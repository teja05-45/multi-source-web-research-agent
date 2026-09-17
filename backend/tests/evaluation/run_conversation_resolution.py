"""Deterministic evaluation harness for the question-resolution core.

Runs 30 realistic follow-up scenarios through the deterministic (heuristic)
resolver — no LLM, no network, fully hermetic — and reports ACTUAL per-case
outcomes: whether every expected subject survives into the resolved question,
whether the active topic was selected correctly, and whether clarification
was requested exactly when it should be. No fabricated accuracy numbers are
produced; the pass rate below is computed from these recorded outcomes.

Usage:
    cd backend
    python -m tests.evaluation.run_conversation_resolution
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.question_resolution.resolver import resolve_question
from app.question_resolution.state import build_conversation_state

CASES_PATH = Path(__file__).parent / "conversation_resolution_cases.json"


async def evaluate_all() -> dict:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results: list[dict] = []

    for case in cases:
        state = build_conversation_state(
            case.get("history", []),
            case.get("research_records", None),
            current_question=case["current_question"],
        )
        resolution = await resolve_question(case["current_question"], state, llm_client=None)

        combined = (resolution.resolved_question or "").lower()
        subjects_ok = all(s.lower() in combined for s in case.get("expected_subjects", []))

        topic_ok: bool = True
        if case.get("expected_topic"):
            topic_ok = (
                resolution.topic is not None
                and resolution.topic.lower() == case["expected_topic"].lower()
            )

        expect_clarification = bool(case.get("expect_clarification", False))
        clarification_ok = resolution.needs_clarification == expect_clarification

        passed = subjects_ok and topic_ok and clarification_ok

        results.append(
            {
                "id": case["id"],
                "category": case.get("category", "followup"),
                "current_question": case["current_question"],
                "resolved_question": resolution.resolved_question,
                "topic": resolution.topic,
                "intent": resolution.intent.value,
                "needs_clarification": resolution.needs_clarification,
                "subjects_present": subjects_ok,
                "topic_ok": topic_ok,
                "clarification_ok": clarification_ok,
                "passed": passed,
            }
        )

    passed_count = sum(1 for r in results if r["passed"])
    return {
        "cases_evaluated": len(results),
        "passed": passed_count,
        "resolution_accuracy": round(passed_count / len(results), 3) if results else None,
        "per_case_results": results,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(evaluate_all()), indent=2))