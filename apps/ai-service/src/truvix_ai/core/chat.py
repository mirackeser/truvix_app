"""Domain models for AI chat interactions."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ChatRole(StrEnum):
    """Roles in a chat conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ImageAttachment:
    """An image attached to a chat message."""
    data: bytes
    media_type: str

    def as_data_url(self) -> str:
        """Format the image as a base64 data URL."""
        b64_data = base64.b64encode(self.data).decode("utf-8")
        return f"data:{self.media_type};base64,{b64_data}"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A single message in a chat conversation."""
    role: ChatRole
    content: str
    images: list[ImageAttachment] | None = None


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    """The resulting response from a chat model."""
    content: str
    finish_reason: str | None = None


class ChatModel(Protocol):
    """Protocol defining the interface for all chat models."""
    
    async def complete(self, messages: list[ChatMessage]) -> ChatCompletion:
        """
        Generate a completion for the given messages.
        
        Args:
            messages: The conversation history.
            
        Returns:
            ChatCompletion: The generated response.
            
        Raises:
            ExternalServiceError: If the underlying service fails.
        """
        ...
