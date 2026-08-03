"""Persistence models for copilot conversations.

A conversation is anchored to one garage vehicle: the copilot's value is that
it answers about *this* car with its data in context, which is exactly how the
copilot screen presents it.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from truvix.modules.vehicles.models import Vehicle
from truvix.shared.database import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum

MESSAGE_MAX_LENGTH = 4000


class MessageRole(StrEnum):
    """Author of a stored copilot message."""

    USER = "user"
    ASSISTANT = "assistant"


_MESSAGE_ROLE = pg_enum(MessageRole, name="copilot_message_role")


class CopilotConversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A chat thread between one user and the copilot about one vehicle."""

    __tablename__ = "copilot_conversations"
    __table_args__ = (
        Index("ix_copilot_conversations_user_recent", "user_id", text("created_at DESC")),
        Index("ix_copilot_conversations_vehicle_id", "vehicle_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )

    vehicle: Mapped[Vehicle] = relationship()
    messages: Mapped[list[CopilotMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CopilotMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"CopilotConversation(id={self.id!r}, vehicle_id={self.vehicle_id!r})"


class CopilotMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One message within a conversation."""

    __tablename__ = "copilot_messages"
    __table_args__ = (
        Index("ix_copilot_messages_conversation_recent", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("copilot_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(_MESSAGE_ROLE, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    conversation: Mapped[CopilotConversation] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"CopilotMessage(role={self.role.value!r})"
