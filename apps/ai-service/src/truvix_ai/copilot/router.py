"""
API routes for the Copilot module.

Exposes endpoints for user interactions with the Copilot AI assistant.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from truvix_ai.copilot.schemas import CopilotRequest, CopilotResponse
from truvix_ai.copilot.service import CopilotService
from truvix_ai.core.errors import ServiceUnavailableError
from truvix_ai.guardrails.validator import InputValidator
from truvix_ai.config import get_settings

router = APIRouter(prefix='/api/v1/copilot', tags=['Copilot'])


@router.get('/status')
async def get_status(request: Request) -> dict[str, bool]:
    """Returns the availability status of the Copilot service."""
    app = request.app
    chat_model = getattr(app.state, 'chat_model', None)
    return {"available": chat_model is not None}


@router.post('/chat', response_model=CopilotResponse)
async def chat(request: Request, body: CopilotRequest) -> CopilotResponse:
    """Processes a user message and returns the assistant's reply."""
    app = request.app
    chat_model = getattr(app.state, 'chat_model', None)
    
    if chat_model is None:
        raise ServiceUnavailableError("Chat model is not configured.")
        
    settings = get_settings()
    
    validator = InputValidator()
    if not validator.validate(body.message):
        raise HTTPException(status_code=400, detail="Invalid or unsafe input detected.")
        
    service = CopilotService(model=chat_model, settings=settings)
    
    return await service.chat(body)
