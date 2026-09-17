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

from fastapi import APIRouter, Depends, HTTPException, Query, Request

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
    payload: ResearchRequest,
    conversation_id: str | None = Query(None, description="Optional conversation ID for context"),
    pipeline: ResearchPipeline = Depends(get_pipeline),
    request: Request = None,
) -> ResearchReport:
    try:
        # If conversation_id provided, resolve follow-up questions against history
        resolution = None
        if conversation_id:
            from app.database import session_scope
            from app.question_resolution.resolver import resolve_question
            from app.question_resolution.state import build_conversation_state
            from app.repositories.conversation_repo import MessageRepository, ResearchRequestRepository

            async with session_scope() as session:
                msg_repo = MessageRepository(session)
                research_repo = ResearchRequestRepository(session)
                message_rows = await msg_repo.list_by_conversation(conversation_id, limit=200)
                record_rows = await research_repo.list_by_conversation(conversation_id, limit=50)
                state = build_conversation_state(
                    [{"role": m.role, "content": m.content} for m in message_rows],
                    [{"status": r.status, "request_payload": r.request_payload} for r in record_rows],
                    current_question=payload.question,
                )
                resolution = await resolve_question(
                    payload.question,
                    state,
                    llm_client=request.app.state.pipeline._llm_client,
                )

        return await pipeline.run(payload, resolution=resolution)
    except ResearchAgentError as exc:
        logger.error("research_request_failed", extra={"error_code": exc.code.value, "message": exc.message})
        raise HTTPException(status_code=502, detail={"error_code": exc.code.value, "message": exc.message}) from exc
    except Exception as exc:  # last-resort safety net: never leak stack traces to clients
        logger.exception("research_request_unhandled_error")
        raise HTTPException(
            status_code=500,
            detail={"error_code": "internal_error", "message": "An unexpected error occurred while processing this request."},
        ) from exc
