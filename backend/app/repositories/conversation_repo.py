"""Repository layer for conversation data access."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message, ResearchRequest


class ConversationRepository:
    """Data access for conversations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, title: str = "New Research") -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(title=title)
        self._session.add(conversation)
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation

    async def get_by_id(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Conversation]:
        """List conversations with optional filtering and search."""
        query = select(Conversation)

        if status:
            query = query.where(Conversation.status == status)

        if search:
            query = query.where(Conversation.title.ilike(f"%{search}%"))

        query = query.order_by(desc(Conversation.updated_at)).limit(limit).offset(offset)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count conversations with optional filtering."""
        query = select(func.count(Conversation.id))

        if status:
            query = query.where(Conversation.status == status)

        if search:
            query = query.where(Conversation.title.ilike(f"%{search}%"))

        result = await self._session.execute(query)
        return result.scalar_one()

    async def update(self, conversation: Conversation) -> Conversation:
        """Update a conversation."""
        conversation.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation

    async def delete(self, conversation_id: str) -> bool:
        """Delete a conversation by ID."""
        conversation = await self.get_by_id(conversation_id)
        if conversation:
            await self._session.delete(conversation)
            await self._session.flush()
            return True
        return False

    async def archive(self, conversation_id: str) -> Optional[Conversation]:
        """Archive a conversation."""
        conversation = await self.get_by_id(conversation_id)
        if conversation:
            conversation.status = "archived"
            conversation.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            await self._session.refresh(conversation)
        return conversation

    async def unarchive(self, conversation_id: str) -> Optional[Conversation]:
        """Unarchive a conversation."""
        conversation = await self.get_by_id(conversation_id)
        if conversation:
            conversation.status = "active"
            conversation.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            await self._session.refresh(conversation)
        return conversation


class MessageRepository:
    """Data access for messages."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        conversation_id: str,
        role: str,
        content: str,
        research_request_id: Optional[str] = None,
    ) -> Message:
        """Create a new message."""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            research_request_id=research_request_id,
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def get_by_id(self, message_id: str) -> Optional[Message]:
        """Get a message by ID."""
        result = await self._session.execute(
            select(Message).where(Message.id == message_id)
        )
        return result.scalar_one_or_none()

    async def list_by_conversation(
        self,
        conversation_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Message]:
        """List messages for a conversation in chronological order."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_by_conversation(self, conversation_id: str) -> int:
        """Count messages in a conversation."""
        query = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        result = await self._session.execute(query)
        return result.scalar_one()

    async def get_last_n(
        self, conversation_id: str, n: int = 5
    ) -> List[Message]:
        """Get the last N messages for a conversation (for context)."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(n)
        )
        result = await self._session.execute(query)
        messages = list(result.scalars().all())
        return list(reversed(messages))  # Return in chronological order


class ResearchRequestRepository:
    """Data access for research requests."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        conversation_id: str,
        question: str,
        request_payload: dict,
    ) -> ResearchRequest:
        """Create a new research request."""
        research_request = ResearchRequest(
            conversation_id=conversation_id,
            question=question,
            status="pending",
            request_payload=request_payload,
        )
        self._session.add(research_request)
        await self._session.flush()
        await self._session.refresh(research_request)
        return research_request

    async def get_by_id(self, request_id: str) -> Optional[ResearchRequest]:
        """Get a research request by ID."""
        result = await self._session.execute(
            select(ResearchRequest).where(ResearchRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        request_id: str,
        status: str,
        response_payload: Optional[dict] = None,
    ) -> Optional[ResearchRequest]:
        """Update research request status and response."""
        result = await self._session.execute(
            select(ResearchRequest).where(ResearchRequest.id == request_id)
        )
        request = result.scalar_one_or_none()
        if request:
            request.status = status
            if response_payload is not None:
                request.response_payload = response_payload
            await self._session.flush()
            await self._session.refresh(request)
        return request

    async def list_by_conversation(
        self, conversation_id: str, limit: int = 20
    ) -> List[ResearchRequest]:
        """List research requests for a conversation."""
        query = (
            select(ResearchRequest)
            .where(ResearchRequest.conversation_id == conversation_id)
            .order_by(desc(ResearchRequest.created_at))
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())