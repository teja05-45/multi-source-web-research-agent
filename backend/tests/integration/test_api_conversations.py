"""API-level tests for the conversation research flow.

Regression guard for the production bug where a response-model mismatch
(``response_model=dict`` alongside a ``ResearchResponse`` return value) caused
an empty-body 500 *without* CORS headers, which the browser surfaced as an
opaque ``TypeError: Failed to fetch``.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.errors import ProviderError
from app.models.query import ResearchRequest
from app.models.report import TraceResolution
from app.models.report import ResearchReport, ResearchTrace


def _valid_report(request_id: str = "test-request-id", question: str = "test") -> ResearchReport:
    return ResearchReport(
        request_id=request_id,
        question=question,
        answer="A test answer.",
        key_claims=[],
        sources=[],
        conflicts=[],
        uncertainties=[],
        research_trace=ResearchTrace(
            request_id=request_id,
            subqueries=0,
            providers_attempted=1,
            providers_succeeded=1,
            results_retrieved=0,
            duplicates_removed=0,
            sources_fetched=0,
            evidence_items=0,
            conflicts_detected=0,
        ),
    )


class _FakePipeline:
    _llm_client = None

    def __init__(self):
        self.resolutions: list = []

    async def run(self, request: ResearchRequest, *, resolution=None) -> ResearchReport:
        self.resolutions.append(resolution)
        report = _valid_report(question=request.question)
        if resolution is not None:
            report.research_trace.resolution = TraceResolution(
                raw_question=resolution.raw_question,
                resolved_question=resolution.resolved_question,
                topic=resolution.topic,
                is_follow_up=resolution.is_follow_up,
                intent=resolution.intent.value if resolution.intent else "new_independent",
                referenced_entities=list(resolution.referenced_entities),
                confidence=resolution.confidence,
                needs_clarification=resolution.needs_clarification,
                method=resolution.method,
            )
        return report


class _FailingPipeline:
    _llm_client = None

    async def run(self, request: ResearchRequest, *, resolution=None):
        raise ProviderError(
            "Search provider timed out.",
            provider="tavily",
            retryable=True,
        )


@pytest.fixture
def client():
    with TestClient(app) as c:
        app.state.pipeline = _FakePipeline()
        yield c


def _create_conversation(client, title="Test conversation"):
    response = client.post("/api/conversations", json={"title": title})
    assert response.status_code == 201
    return response.json()


def test_conversation_research_returns_research_response_shape(client):
    """Regression test: the response must serialize as ResearchResponse, not
    silently break serialization and return an empty 500."""
    conv = _create_conversation(client)
    response = client.post(
        f"/api/conversations/{conv['id']}/research",
        json={"question": "Acoustic ocean monitoring systems in 2025"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "request_id",
        "question",
        "answer",
        "key_claims",
        "sources",
        "conflicts",
        "uncertainties",
        "research_trace",
        "degraded",
    }
    assert body["answer"] == "A test answer."


def test_conversation_research_persists_user_and_assistant_messages(client):
    conv = _create_conversation(client)
    response = client.post(
        f"/api/conversations/{conv['id']}/research",
        json={"question": "Acoustic ocean monitoring systems in 2025"},
        headers={"X-Request-ID": "persist-me-42"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "persist-me-42"

    messages = client.get(f"/api/conversations/{conv['id']}/messages").json()
    assert len(messages) == 2
    assert [m["role"] for m in messages] == ["user", "assistant"]

    assistant = messages[1]
    content = json.loads(assistant["content"])
    assert content["request_id"] == "persist-me-42"
    assert content["answer"] == "A test answer."


def test_conversation_research_carries_request_id_header(client):
    conv = _create_conversation(client)
    response = client.post(
        f"/api/conversations/{conv['id']}/research",
        json={"question": "Acoustic ocean monitoring systems in 2025"},
        headers={"X-Request-ID": "trace-me-123"},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-me-123"


def test_followup_question_is_resolved_to_active_topic_before_pipeline(client):
    """Regression test for the JS-u2013Python bug: a pronoun follow-up like
    'why it differ from other programming language' after 'What is
    JavaScript?' must reach the pipeline resolved to JavaScript, and the
    resolution must be persisted in the research request."""
    pipeline = _FakePipeline()
    app.state.pipeline = pipeline

    conv = _create_conversation(client)
    first = client.post(
        f"/api/conversations/{conv['id']}/research",
        json={"question": "What is JavaScript?"},
    )
    assert first.status_code == 200
    assert first.json()["research_trace"]["resolution"]["topic"] == "JavaScript"
    assert first.json()["research_trace"]["resolution"]["is_follow_up"] is False

    second = client.post(
        f"/api/conversations/{conv['id']}/research",
        json={"question": "why it differ from other programming language"},
    )
    assert second.status_code == 200
    trace_resolution = second.json()["research_trace"]["resolution"]
    assert trace_resolution["resolved_question"].count("JavaScript") > 0
    assert trace_resolution["topic"] == "JavaScript"
    assert trace_resolution["is_follow_up"] is True

    # The pipeline received the resolved question, not the raw pronoun.
    assert len(pipeline.resolutions) == 2
    assert pipeline.resolutions[1] is not None
    assert "JavaScript" in pipeline.resolutions[1].resolved_question

    # The resolution metadata was persisted on the research request payload.
    messages = client.get(f"/api/conversations/{conv['id']}/messages").json()
    second_answer = json.loads(messages[3]["content"])
    assert second_answer["research_trace"]["resolution"]["resolved_question"] == (
        trace_resolution["resolved_question"]
    )


def test_ambiguous_followup_asks_for_clarification_without_calling_pipeline(client):
    """A pronoun with no active topic must not guess nor hit providers."""
    pipeline = _FakePipeline()
    app.state.pipeline = pipeline

    conv = _create_conversation(client)
    response = client.post(
        f"/api/conversations/{conv['id']}/research",
        json={"question": "Why is it popular?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["research_trace"]["resolution"]["needs_clarification"] is True
    assert body["research_trace"]["resolution"]["topic"] is None

    # No research happened (the pipeline was never reached).
    assert pipeline.resolutions == []
    messages = client.get(f"/api/conversations/{conv['id']}/messages").json()
    assert len(messages) == 2  # user + clarification assistant message


def test_conversation_research_failure_returns_error_envelope(client):
    """A pipeline failure must produce a structured, CORS-safe error envelope
    (never an opaque empty 500) and persist a failed state + failure message."""
    app.state.pipeline = _FailingPipeline()
    conv = _create_conversation(client)
    response = client.post(
        f"/api/conversations/{conv['id']}/research",
        json={"question": "Acoustic ocean monitoring systems in 2025"},
    )
    assert response.status_code == 502
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "provider_error"
    assert body["error"]["retryable"] is True
    assert body["error"]["request_id"]

    # User question must still be kept, with a failure marker from the assistant.
    messages = client.get(f"/api/conversations/{conv['id']}/messages").json()
    assert len(messages) == 2
    assistant = json.loads(messages[1]["content"])
    assert assistant["error"]["code"] == "provider_error"
    assert assistant["error"]["request_id"] == body["error"]["request_id"]


def test_conversation_research_unknown_conversation_returns_404_envelope(client):
    response = client.post(
        "/api/conversations/does-not-exist/research",
        json={"question": "Acoustic ocean monitoring systems in 2025"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"


def test_conversation_research_empty_question_returns_validation_envelope(client):
    conv = _create_conversation(client)
    response = client.post(
        f"/api/conversations/{conv['id']}/research",
        json={"question": ""},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["retryable"] is False


def test_conversation_crud(client):
    conv = _create_conversation(client)
    assert conv["message_count"] == 0

    listed = client.get("/api/conversations").json()
    assert any(c["id"] == conv["id"] for c in listed)

    fetched = client.get(f"/api/conversations/{conv['id']}").json()
    assert fetched["title"] == "Test conversation"

    renamed = client.patch(f"/api/conversations/{conv['id']}", json={"title": "Renamed"}).json()
    assert renamed["title"] == "Renamed"

    deleted = client.delete(f"/api/conversations/{conv['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/conversations/{conv['id']}").status_code == 404