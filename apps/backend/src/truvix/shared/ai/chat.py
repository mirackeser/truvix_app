"""Provider-agnostic chat model interface.

Everything above this seam — the analysis engine, the copilot — speaks in these
types. Swapping OpenAI for another provider, or moving inference into its own
service, means writing one new implementation of ``ChatModel`` and touching
nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ChatRole(StrEnum):
    """Author of a chat message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message in a conversation sent to the model."""

    role: ChatRole
    content: str


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    """The model's reply and its accounting."""

    content: str
    input_tokens: int
    output_tokens: int


class ChatModel(Protocol):
    """Interface every chat-capable model client implements."""

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        json_response: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatCompletion:
        """Send a conversation and return the model's reply.

        Args:
            messages: The conversation so far, oldest first.
            json_response: Whether the model must reply with a JSON object.
            max_output_tokens: Optional ceiling on the reply's length.

        Raises:
            ExternalServiceError: If the provider cannot produce a reply.
        """
        ...
