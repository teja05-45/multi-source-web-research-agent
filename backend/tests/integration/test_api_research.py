"""API-level tests for POST /api/research, with the pipeline swapped for a
fake at app.state so no real network calls happen.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.query import ResearchRequest
from app.models.report import ResearchReport, ResearchTrace


class _FakePipeline:
    async def run(self, request: ResearchRequest, *, resolution=None) -> ResearchReport:
        return ResearchReport(
            request_id="test-request-id",
            question=request.question,
            answer="A test answer.",
            key_claims=[],
            sources=[],
            conflicts=[],
            uncertainties=[],
            research_trace=ResearchTrace(
                request_id="test-request-id",
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


@pytest.fixture
def client():
    with TestClient(app) as c:
        app.state.pipeline = _FakePipeline()
        yield c


def test_research_endpoint_returns_valid_report(client):
    response = client.post("/api/research", json={"question": "What is the capital of France?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "A test answer."
    assert body["question"] == "What is the capital of France?"


def test_research_endpoint_rejects_empty_question(client):
    response = client.post("/api/research", json={"question": ""})
    assert response.status_code == 422


def test_research_endpoint_rejects_overlong_question(client):
    response = client.post("/api/research", json={"question": "x" * 5000})
    assert response.status_code == 422


def test_research_endpoint_rejects_missing_question_field(client):
    response = client.post("/api/research", json={})
    assert response.status_code == 422
