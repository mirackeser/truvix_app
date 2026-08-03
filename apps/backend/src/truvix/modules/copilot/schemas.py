"""Request and response models for the copilot endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field

from truvix.modules.copilot.models import (
    MESSAGE_MAX_LENGTH,
    CopilotConversation,
    CopilotMessage,
    MessageRole,
)


class ConversationOpenRequest(BaseModel):
    """Payload for opening (or resuming) a conversation about a vehicle."""

    vehicle_id: uuid.UUID


class MessageSendRequest(BaseModel):
    """Payload for sending one user message."""

    model_config = ConfigDict(str_strip_whitespace=True)

    content: Annotated[str, Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)]


class MessageResponse(BaseModel):
    """One stored message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime

    @classmethod
    def from_message(cls, message: CopilotMessage) -> Self:
        """Build the response from a persisted message."""
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )


class ConversationResponse(BaseModel):
    """A conversation and the vehicle it is about."""

    id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_display_name: str
    created_at: datetime

    @classmethod
    def from_conversation(cls, conversation: CopilotConversation) -> Self:
        """Build the response from a persisted conversation with its vehicle."""
        return cls(
            id=conversation.id,
            vehicle_id=conversation.vehicle_id,
            vehicle_display_name=conversation.vehicle.display_name,
            created_at=conversation.created_at,
        )


class ConversationDetailResponse(BaseModel):
    """A conversation with its full message history."""

    conversation: ConversationResponse
    messages: list[MessageResponse]


class MessageExchangeResponse(BaseModel):
    """The user's stored message together with the assistant's reply."""

    user_message: MessageResponse
    assistant_message: MessageResponse


class CopilotStatusResponse(BaseModel):
    """Whether AI assistance is available on this deployment."""

    available: bool
