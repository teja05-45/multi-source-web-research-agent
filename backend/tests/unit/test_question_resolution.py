"""Unit tests for the deterministic question-resolution core.

These mirror the 10 prescribed acceptance scenarios plus ambiguity handling.
The heuristic path is exercised directly (no LLM) so the tests are hermetic:
build_conversation_state needs no DB and resolve_question skips LLM polish
when no client is supplied.
"""
from __future__ import annotations

from app.question_resolution.models import QuestionIntent
from app.question_resolution.resolver import resolve_heuristic, resolve_question
from app.question_resolution.state import build_conversation_state


def _resolved(history_qas: list[tuple[str, str]], current: str):
    """Build state from a list of (question, answer) turns, then resolve."""
    messages: list[dict] = []
    for question, answer in history_qas:
        messages.append({"role": "user", "content": question})
        messages.append(
            {"role": "assistant", "content": f'{{"answer": "{answer}", "question": "{question}"}}'}
        )
    state = build_conversation_state(messages, None, current_question=current)
    return resolve_heuristic(current, state)


def _assert_subject(resolution, *expected_subjects):
    """The resolved question must mention every expected subject and the
    topic must be one of them."""
    combined = resolution.resolved_question.lower()
    for subject in expected_subjects:
        assert subject.lower() in combined, (
            f"resolved question {resolution.resolved_question!r} must mention {subject!r}"
        )
    assert resolution.topic is not None
    assert any(resolution.topic.lower() == s.lower() for s in expected_subjects)
    assert resolution.needs_clarification is False


def _run(current: str):
    """A sync shim around the async entry point (no LLM client → heuristic)."""
    import asyncio

    async def _inner():
        state = build_conversation_state([], None, current_question=current)
        return await resolve_question(current, state, llm_client=None)

    return asyncio.run(_inner())


# --- The 10 prescribed acceptance tests ------------------------------------


def test_1_followup_why_is_it_popular_resolves_to_javascript():
    resolution = _resolved([("What is JavaScript?", "JavaScript is a language.")], "Why is it popular?")
    _assert_subject(resolution, "JavaScript")
    assert resolution.intent is QuestionIntent.FOLLOW_UP
    assert resolution.is_follow_up is True


def test_2_followup_differ_from_other_languages_keeps_javascript():
    resolution = _resolved(
        [("What is JavaScript?", "JavaScript is a language.")],
        "Why does it differ from other programming languages?",
    )
    _assert_subject(resolution, "JavaScript")


def test_3_same_followup_after_python_resolves_to_python():
    resolution = _resolved(
        [("What is Python?", "Python is a language.")],
        "Why does it differ from other programming languages?",
    )
    _assert_subject(resolution, "Python")


def test_4_explicit_new_topic_python_switches_subject():
    resolution = _resolved([("What is JavaScript?", "JavaScript is a language.")], "How is Python different?")
    _assert_subject(resolution, "Python")
    # The pronoun-free explicit topic must NOT inherit JavaScript.
    assert "javascript" not in resolution.resolved_question.lower()


def test_5_comparison_compare_it_with_python_keeps_both_entities():
    resolution = _resolved([("What is JavaScript?", "JavaScript is a language.")], "Compare it with Python.")
    _assert_subject(resolution, "JavaScript", "Python")
    assert "JavaScript" in resolution.referenced_entities
    assert "Python" in resolution.referenced_entities
    assert resolution.intent is QuestionIntent.COMPARISON


def test_6_why_is_it_used_after_react_resolves_to_react():
    resolution = _resolved([("What is React?", "React is a library.")], "Why is it used?")
    _assert_subject(resolution, "React")


def test_7_what_is_its_revenue_after_tesla_resolves_to_tesla():
    resolution = _resolved([("What is Tesla?", "Tesla is a car maker.")], "What is its revenue?")
    _assert_subject(resolution, "Tesla")


def test_8_tell_me_about_databases_starts_new_topic_without_js_leak():
    resolution = _resolved([("What is JavaScript?", "JavaScript is a language.")], "Tell me about databases.")
    assert resolution.needs_clarification is False
    assert "JavaScript" not in resolution.resolved_question.lower()


def test_9_three_turn_javascript_continuity():
    messages = [
        {"role": "user", "content": "What is JavaScript?"},
        {"role": "assistant", "content": '{"answer": "JS is a language.", "research_trace": {"resolution": {"topic": "JavaScript"}}}'},
        {"role": "user", "content": "Why is it popular?"},
        {"role": "assistant", "content": '{"answer": "popular"}'},
        {"role": "user", "content": "What are its disadvantages?"},
    ]
    state = build_conversation_state(messages, None, current_question="What are its disadvantages?")
    resolution = resolve_heuristic("What are its disadvantages?", state)
    _assert_subject(resolution, "JavaScript")


def test_10_topic_change_then_followup_resolves_to_latest_topic():
    messages = [
        {"role": "user", "content": "What is JavaScript?"},
        {"role": "assistant", "content": '{"answer": "JavaScript is a language."}'},
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": '{"answer": "Python is a language."}'},
        {"role": "user", "content": "Why is it popular?"},
    ]
    state = build_conversation_state(messages, None, current_question="Why is it popular?")
    resolution = resolve_heuristic("Why is it popular?", state)
    _assert_subject(resolution, "Python")


# --- Ambiguity handling -----------------------------------------------------


def test_pronoun_without_active_topic_asks_for_clarification():
    resolution = _resolved([], "Why is it popular?")
    assert resolution.needs_clarification is True
    assert resolution.intent is QuestionIntent.AMBIGUOUS
    assert resolution.resolved_question == "Why is it popular?"  # never guessed


def test_pronoun_without_topic_but_with_explicit_entity_is_resolved():
    resolution = _resolved([], "Why is Python popular?")
    assert resolution.needs_clarification is False
    _assert_subject(resolution, "Python")


def test_exact_reproducion_case_resolves_to_javascript():
    resolution = _resolved(
        [("What is JavaScript?", "JavaScript is a language.")],
        "why it differ from other programming language",
    )
    _assert_subject(resolution, "JavaScript")


def test_new_independent_question_skips_resolution():
    resolution = _run("What is the capital of France?")
    assert resolution.is_follow_up is False
    assert resolution.topic == "France"
    assert resolution.resolved_question == "What is the capital of France?"