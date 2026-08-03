"""Data access for copilot conversations, always scoped to their owner."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from truvix.modules.copilot.models import CopilotConversation, CopilotMessage
from truvix.shared.pagination import PageParams


class CopilotRepository:
    """Reads and writes conversations and their messages."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the repository.

        Args:
            session: The session whose transaction this repository participates in.
        """
        self._session = session

    async def get_for_owner(
        self, *, owner_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> CopilotConversation | None:
        """Fetch one of the owner's conversations with its vehicle loaded.

        Args:
            owner_id: The account the conversation must belong to.
            conversation_id: The conversation to fetch.
        """
        statement = (
            select(CopilotConversation)
            .where(
                CopilotConversation.id == conversation_id,
                CopilotConversation.user_id == owner_id,
            )
            .options(joinedload(CopilotConversation.vehicle))
        )
        conversation: CopilotConversation | None = await self._session.scalar(statement)
        return conversation

    async def find_for_vehicle(
        self, *, owner_id: uuid.UUID, vehicle_id: uuid.UUID
    ) -> CopilotConversation | None:
        """Find the owner's existing conversation about a vehicle, if any.

        Args:
            owner_id: The account whose conversation to look for.
            vehicle_id: The vehicle the conversation is about.
        """
        statement = (
            select(CopilotConversation)
            .where(
                CopilotConversation.user_id == owner_id,
                CopilotConversation.vehicle_id == vehicle_id,
            )
            .options(joinedload(CopilotConversation.vehicle))
            .order_by(CopilotConversation.created_at.desc())
            .limit(1)
        )
        conversation: CopilotConversation | None = await self._session.scalar(statement)
        return conversation

    async def list_for_owner(
        self, *, owner_id: uuid.UUID, params: PageParams
    ) -> tuple[Sequence[CopilotConversation], int]:
        """List a page of the owner's conversations, newest first.

        Args:
            owner_id: The account whose conversations to list.
            params: Pagination parameters.
        """
        base = select(CopilotConversation).where(CopilotConversation.user_id == owner_id)
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))

        listing = (
            base.options(joinedload(CopilotConversation.vehicle))
            .order_by(CopilotConversation.created_at.desc(), CopilotConversation.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        result = await self._session.scalars(listing)
        return result.all(), int(total or 0)

    async def recent_messages(
        self, *, conversation_id: uuid.UUID, limit: int
    ) -> Sequence[CopilotMessage]:
        """Read the newest messages of a conversation, returned oldest first.

        Args:
            conversation_id: The conversation to read.
            limit: Maximum number of messages to return.
        """
        newest_first = (
            select(CopilotMessage)
            .where(CopilotMessage.conversation_id == conversation_id)
            .order_by(CopilotMessage.created_at.desc(), CopilotMessage.id.desc())
            .limit(limit)
        )
        result = await self._session.scalars(newest_first)
        return list(reversed(result.all()))

    async def all_messages(self, *, conversation_id: uuid.UUID) -> Sequence[CopilotMessage]:
        """Read a conversation's full history, oldest first.

        Args:
            conversation_id: The conversation to read.
        """
        statement = (
            select(CopilotMessage)
            .where(CopilotMessage.conversation_id == conversation_id)
            .order_by(CopilotMessage.created_at.asc(), CopilotMessage.id.asc())
        )
        result = await self._session.scalars(statement)
        return result.all()

    def add(self, conversation: CopilotConversation) -> None:
        """Stage a new conversation for insertion."""
        self._session.add(conversation)

    def add_message(self, message: CopilotMessage) -> None:
        """Stage a new message for insertion."""
        self._session.add(message)

    async def flush(self) -> None:
        """Send pending changes to the database without committing."""
        await self._session.flush()
