"""Conversation API routes."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.routes.research import get_pipeline
from app.database import get_session, session_scope
from app.models.conversation import Message
from app.models.errors import ErrorCode, ResearchAgentError
from app.models.query import ResearchRequest
from app.models.report import ResearchReport, ResearchTrace, TraceResolution
from app.observability.logging import get_request_id
from app.orchestration.research_pipeline import ResearchPipeline
from app.question_resolution.models import QuestionResolution
from app.question_resolution.resolver import resolve_question
from app.question_resolution.state import build_conversation_state
from app.repositories.conversation_repo import (
    ConversationRepository,
    MessageRepository,
    ResearchRequestRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

_RETRYABLE_CODES = {ErrorCode.PROVIDER_ERROR, ErrorCode.ALL_PROVIDERS_FAILED, ErrorCode.FETCH_ERROR, ErrorCode.LLM_ERROR}

_CLARIFICATION_ANSWER = (
    "I couldn't tell which subject you'd like me to research from that question alone. "
    "Could you name the topic explicitly? For example, tell me which programming language, "
    "product, company, or concept you're asking about."
)


async def _resolve_context(
    conversation_id: str, question: str, pipeline: ResearchPipeline
) -> QuestionResolution:
    """Resolve a question against stored conversation history."""
    async with session_scope() as ctx_session:
        ctx_msg_repo = MessageRepository(ctx_session)
        ctx_research_repo = ResearchRequestRepository(ctx_session)

        message_rows = await ctx_msg_repo.list_by_conversation(conversation_id, limit=200)
        messages = [{"role": m.role, "content": m.content} for m in message_rows]

        record_rows = await ctx_research_repo.list_by_conversation(conversation_id, limit=50)
        research_records = [
            {"status": r.status, "request_payload": r.request_payload}
            for r in record_rows
        ]

        state = build_conversation_state(messages, research_records, current_question=question)
        return await resolve_question(question, state, llm_client=pipeline._llm_client)


def _clarification_report(
    request: ResearchRequest,
    resolution: QuestionResolution,
    request_id: str,
) -> ResearchReport:
    """Build a no-research report that asks the user to clarify the subject."""
    from app.models.claims import Uncertainty

    return ResearchReport(
        request_id=request_id,
        question=request.question,
        answer=_CLARIFICATION_ANSWER,
        key_claims=[],
        sources=[],
        conflicts=[],
        uncertainties=[
            Uncertainty(
                description="The question was ambiguous: pronouns were used but no active topic "
                "could be resolved from the conversation.",
                reason="needs_clarification",
            )
        ],
        research_trace=ResearchTrace(
            request_id=request_id,
            subqueries=0,
            providers_attempted=0,
            providers_succeeded=0,
            results_retrieved=0,
            duplicates_removed=0,
            sources_fetched=0,
            evidence_items=0,
            conflicts_detected=0,
            total_latency_ms=0.0,
            resolution=TraceResolution(
                raw_question=resolution.raw_question,
                resolved_question=resolution.resolved_question,
                topic=resolution.topic,
                is_follow_up=resolution.is_follow_up,
                intent=resolution.intent.value,
                referenced_entities=list(resolution.referenced_entities),
                confidence=resolution.confidence,
                needs_clarification=True,
                method=resolution.method,
            ),
        ),
        degraded=False,
        status="needs_clarification",
    )


def _classify_failure(exc: Exception) -> tuple[str, str]:
    """Map a pipeline failure to an error code and human-readable message."""
    if isinstance(exc, ResearchAgentError):
        return exc.code.value, exc.message
    return ErrorCode.INTERNAL_ERROR.value, "The research engine failed unexpectedly."


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, ResearchAgentError):
        return exc.code in _RETRYABLE_CODES
    return True

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# --- Request/Response Models ---

class ConversationCreate(BaseModel):
    title: str = Field(default="New Research", max_length=500)


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, pattern="^(active|archived)$")


class ConversationResponse(BaseModel):
    id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    message_count: int = 0

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str
    research_request_id: str | None = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    research_request_id: str | None
    created_at: str

    class Config:
        from_attributes = True


class ResearchRequestCreate(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    max_sources: int = Field(default=8, ge=1, le=20)
    providers: list[str] | None = None
    depth: str = Field(default="standard", pattern="^(quick|standard)$")


class ResearchResponse(BaseModel):
    request_id: str
    question: str
    answer: str
    key_claims: list[dict]
    sources: list[dict]
    conflicts: list[dict]
    uncertainties: list[dict]
    research_trace: dict
    degraded: bool


# --- Dependencies ---

def get_conversation_repo(session: AsyncSession = Depends(get_session)) -> ConversationRepository:
    return ConversationRepository(session)


def get_message_repo(session: AsyncSession = Depends(get_session)) -> MessageRepository:
    return MessageRepository(session)


def get_research_repo(session: AsyncSession = Depends(get_session)) -> ResearchRequestRepository:
    return ResearchRequestRepository(session)


# --- Routes ---

@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Create a new research conversation."""
    conversation = await repo.create(payload.title)
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
        message_count=0,
    )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    status: str | None = Query(None, pattern="^(active|archived)$"),
    search: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """List conversations with optional filtering and search."""
    conversations = await repo.list(status=status, search=search, limit=limit, offset=offset)
    result = []
    for conv in conversations:
        msg_count = await repo._session.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conv.id)
        )
        count = msg_count.scalar_one()
        result.append(ConversationResponse(
            id=conv.id,
            title=conv.title,
            status=conv.status,
            created_at=conv.created_at.isoformat(),
            updated_at=conv.updated_at.isoformat(),
            message_count=count,
        ))
    return result


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Get a conversation by ID."""
    conversation = await repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    msg_count = await repo._session.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation.id)
    )
    count = msg_count.scalar_one()
    
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
        message_count=count,
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Update a conversation (rename or archive)."""
    conversation = await repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if payload.title is not None:
        conversation.title = payload.title
    if payload.status is not None:
        conversation.status = payload.status

    updated = await repo.update(conversation)
    msg_count = await repo._session.execute(
        select(func.count(Message.id)).where(Message.conversation_id == updated.id)
    )
    count = msg_count.scalar_one()

    return ConversationResponse(
        id=updated.id,
        title=updated.title,
        status=updated.status,
        created_at=updated.created_at.isoformat(),
        updated_at=updated.updated_at.isoformat(),
        message_count=count,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Delete a conversation."""
    deleted = await repo.delete(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    msg_repo: MessageRepository = Depends(get_message_repo),
    conv_repo: ConversationRepository = Depends(get_conversation_repo),
):
    """List messages for a conversation."""
    conversation = await conv_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await msg_repo.list_by_conversation(conversation_id, limit=limit, offset=offset)
    return [
        MessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            research_request_id=m.research_request_id,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(
    conversation_id: str,
    payload: MessageCreate,
    msg_repo: MessageRepository = Depends(get_message_repo),
    conv_repo: ConversationRepository = Depends(get_conversation_repo),
):
    """Add a message to a conversation."""
    conversation = await conv_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message = await msg_repo.create(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
        research_request_id=payload.research_request_id,
    )
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        research_request_id=message.research_request_id,
        created_at=message.created_at.isoformat(),
    )


@router.post("/{conversation_id}/research", response_model=ResearchResponse)
async def run_research_in_conversation(
    conversation_id: str,
    payload: ResearchRequestCreate,
    conv_repo: ConversationRepository = Depends(get_conversation_repo),
    msg_repo: MessageRepository = Depends(get_message_repo),
    research_repo: ResearchRequestRepository = Depends(get_research_repo),
    pipeline: ResearchPipeline = Depends(get_pipeline),
):
    """Run research within a conversation, with context resolution for follow-ups."""
    request_id = get_request_id()
    conversation = await conv_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await msg_repo.create(
        conversation_id=conversation_id,
        role="user",
        content=payload.question,
    )

    resolution = await _resolve_context(conversation_id, payload.question, pipeline)

    request_payload = payload.model_dump()
    request_payload["resolution"] = resolution.to_dict()

    research_request = await research_repo.create(
        conversation_id=conversation_id,
        question=payload.question,
        request_payload=request_payload,
    )
    await research_repo.update_status(research_request.id, "running")

    request = ResearchRequest(
        question=payload.question,
        max_sources=payload.max_sources,
        providers=payload.providers,
        depth=payload.depth,
    )

    if resolution.needs_clarification:
        report = _clarification_report(request, resolution, request_id)
        await research_repo.update_status(
            research_request.id,
            "needs_clarification",
            response_payload=report.model_dump(mode="json"),
        )
        payload_dict = report.model_dump(mode="json")
        payload_dict["request_id"] = request_id
        payload_dict["research_trace"]["request_id"] = request_id
        await msg_repo.create(
            conversation_id=conversation_id,
            role="assistant",
            content=json.dumps(payload_dict),
            research_request_id=research_request.id,
        )
        await research_repo._session.commit()
        return ResearchResponse(
            request_id=payload_dict["request_id"],
            question=payload_dict["question"],
            answer=payload_dict["answer"],
            key_claims=payload_dict["key_claims"],
            sources=payload_dict["sources"],
            conflicts=payload_dict["conflicts"],
            uncertainties=payload_dict["uncertainties"],
            research_trace=payload_dict["research_trace"],
            degraded=payload_dict["degraded"],
        )

    try:
        report = await pipeline.run(request, resolution=resolution)
    except Exception as exc:  # noqa: BLE001 - persist a failed state for observability
        code, message = _classify_failure(exc)
        await research_repo.update_status(
            research_request.id,
            "failed",
            response_payload={"error": {"code": code, "message": message, "request_id": request_id}},
        )
        failure_message = json.dumps(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": request_id,
                    "retryable": _is_retryable(exc),
                }
            }
        )
        await msg_repo.create(
            conversation_id=conversation_id,
            role="assistant",
            content=failure_message,
            research_request_id=research_request.id,
        )
        await research_repo._session.commit()
        raise

    await research_repo.update_status(
        research_request.id,
        "completed",
        response_payload=report.model_dump(mode="json"),
    )

    payload = report.model_dump(mode="json")
    payload["request_id"] = request_id
    payload["research_trace"]["request_id"] = request_id
    assistant_content = json.dumps(payload)
    await msg_repo.create(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        research_request_id=research_request.id,
    )

    return ResearchResponse(
        request_id=payload["request_id"],
        question=payload["question"],
        answer=payload["answer"],
        key_claims=payload["key_claims"],
        sources=payload["sources"],
        conflicts=payload["conflicts"],
        uncertainties=payload["uncertainties"],
        research_trace=payload["research_trace"],
        degraded=payload["degraded"],
    )