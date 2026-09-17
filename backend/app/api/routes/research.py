"""POST /api/research — run the full research pipeline synchronously.

Synchronous (request/response) execution was chosen over an async job-queue
API for this assignment: requests are bounded in time (subquery count,
provider count, and fetch count are all capped), so a client can reasonably
wait for a direct response. See README "Trade-offs" for the discussion of
when an async job API (`GET /api/research/{request_id}`) would be preferred
in production (e.g. deep research requests with many subqueries).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.models.errors import ResearchAgentError
from app.models.query import ResearchRequest
from app.models.report import ResearchReport
from app.orchestration.research_pipeline import ResearchPipeline

logger = logging.getLogger("research_agent.api.research")

router = APIRouter()


def get_pipeline(request: Request) -> ResearchPipeline:
    return request.app.state.pipeline


@router.post("/api/research", response_model=ResearchReport)
async def run_research(
    payload: ResearchRequest, pipeline: ResearchPipeline = Depends(get_pipeline)
) -> ResearchReport:
    try:
        return await pipeline.run(payload)
    except ResearchAgentError as exc:
        logger.error("research_request_failed", extra={"error_code": exc.code.value, "message": exc.message})
        raise HTTPException(status_code=502, detail={"error_code": exc.code.value, "message": exc.message}) from exc
    except Exception as exc:  # last-resort safety net: never leak stack traces to clients
        logger.exception("research_request_unhandled_error")
        raise HTTPException(
            status_code=500,
            detail={"error_code": "internal_error", "message": "An unexpected error occurred while processing this request."},
        ) from exc
