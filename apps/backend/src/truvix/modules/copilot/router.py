"""HTTP endpoints for the AI copilot."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, status

from truvix.modules.auth.dependencies import CurrentUserDep
from truvix.modules.copilot.dependencies import CopilotServiceDep, enforce_copilot_rate_limit
from truvix.modules.copilot.schemas import (
    ConversationDetailResponse,
    ConversationOpenRequest,
    ConversationResponse,
    CopilotStatusResponse,
    MessageExchangeResponse,
    MessageResponse,
    MessageSendRequest,
)
from truvix.shared.errors import PROBLEM_CONTENT_TYPE
from truvix.shared.pagination import Page, PageParamsDep

router = APIRouter(prefix="/copilot", tags=["copilot"])

_PROBLEM: dict[str, Any] = {"content": {PROBLEM_CONTENT_TYPE: {}}}
_UNAUTHORISED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Access token missing or invalid.", **_PROBLEM},
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    **_UNAUTHORISED,
    status.HTTP_404_NOT_FOUND: {
        "description": "No such conversation in this account.",
        **_PROBLEM,
    },
}


@router.get(
    "/status",
    response_model=CopilotStatusResponse,
    summary="Copilot availability",
    description="Reports whether AI assistance is configured on this deployment.",
    responses=_UNAUTHORISED,
)
async def read_status(
    _current_user: CurrentUserDep,
    service: CopilotServiceDep,
) -> CopilotStatusResponse:
    """Report whether the copilot can answer."""
    return CopilotStatusResponse(available=service.is_available)


@router.post(
    "/conversations",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a conversation",
    description=(
        "Opens the caller's conversation about a vehicle, returning the "
        "existing thread when one already exists."
    ),
    responses=_NOT_FOUND,
)
async def open_conversation(
    payload: ConversationOpenRequest,
    current_user: CurrentUserDep,
    service: CopilotServiceDep,
) -> ConversationDetailResponse:
    """Open or resume the conversation about a vehicle."""
    conversation = await service.open_conversation(
        owner_id=current_user.id, vehicle_id=payload.vehicle_id
    )
    _conversation, messages = await service.get_conversation(
        owner_id=current_user.id, conversation_id=conversation.id
    )
    return ConversationDetailResponse(
        conversation=ConversationResponse.from_conversation(conversation),
        messages=[MessageResponse.from_message(message) for message in messages],
    )


@router.get(
    "/conversations",
    response_model=Page[ConversationResponse],
    summary="List conversations",
    description="Returns a page of the caller's conversations, newest first.",
    responses=_UNAUTHORISED,
)
async def list_conversations(
    current_user: CurrentUserDep,
    service: CopilotServiceDep,
    params: PageParamsDep,
) -> Page[ConversationResponse]:
    """List the caller's conversations."""
    conversations, total = await service.list_conversations(owner_id=current_user.id, params=params)
    items = [ConversationResponse.from_conversation(item) for item in conversations]
    return Page[ConversationResponse].create(items=items, total=total, params=params)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Read a conversation",
    description="Returns one conversation with its full message history.",
    responses=_NOT_FOUND,
)
async def read_conversation(
    conversation_id: uuid.UUID,
    current_user: CurrentUserDep,
    service: CopilotServiceDep,
) -> ConversationDetailResponse:
    """Return one of the caller's conversations."""
    conversation, messages = await service.get_conversation(
        owner_id=current_user.id, conversation_id=conversation_id
    )
    return ConversationDetailResponse(
        conversation=ConversationResponse.from_conversation(conversation),
        messages=[MessageResponse.from_message(message) for message in messages],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageExchangeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
    description="Sends a question to the copilot and returns its answer.",
    dependencies=[Depends(enforce_copilot_rate_limit)],
    responses={
        **_NOT_FOUND,
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Message budget exhausted for this account.",
            **_PROBLEM,
        },
        status.HTTP_502_BAD_GATEWAY: {
            "description": "The AI provider failed to reply.",
            **_PROBLEM,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "AI assistance is not configured on this deployment.",
            **_PROBLEM,
        },
    },
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageSendRequest,
    current_user: CurrentUserDep,
    service: CopilotServiceDep,
) -> MessageExchangeResponse:
    """Send a message and return the assistant's reply."""
    user_message, assistant_message = await service.send_message(
        owner_id=current_user.id,
        conversation_id=conversation_id,
        content=payload.content,
    )
    return MessageExchangeResponse(
        user_message=MessageResponse.from_message(user_message),
        assistant_message=MessageResponse.from_message(assistant_message),
    )
