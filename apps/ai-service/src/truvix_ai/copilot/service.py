"""
Service layer for the Copilot module.

Handles the conversational logic, including context building, message history
management, and interaction with the underlying language model.
"""
from __future__ import annotations

from typing import Any

from truvix_ai.core.chat import ChatModel, ChatMessage, ChatRole
from truvix_ai.guardrails.prompts import COPILOT_SYSTEM_PROMPT, COPILOT_CONTEXT_TEMPLATE
from truvix_ai.copilot.schemas import CopilotRequest, CopilotResponse, VehicleContext
from truvix_ai.observability.logging import get_logger

logger = get_logger(__name__)


class CopilotService:
    def __init__(self, model: ChatModel, settings: Any):
        self.model = model
        self.settings = settings
        self.max_history = getattr(settings, 'copilot_max_history', 12)

    def _build_context(self, vehicle: VehicleContext) -> str:
        """
        Formats vehicle data as readable Turkish text.
        """
        context_parts = [
            f"Araç: {vehicle.make} {vehicle.model}",
            f"Yıl: {vehicle.model_year}",
            f"Kilometre: {vehicle.mileage_km} km",
        ]
        
        if vehicle.fuel_type:
            context_parts.append(f"Yakıt Tipi: {vehicle.fuel_type}")
        if vehicle.transmission:
            context_parts.append(f"Vites: {vehicle.transmission}")
        if vehicle.price:
            context_parts.append(f"Fiyat: {vehicle.price} {vehicle.currency}")
        if vehicle.city:
            context_parts.append(f"Şehir: {vehicle.city}")
            
        if vehicle.trust_score is not None:
            context_parts.append(f"Güven Skoru: {vehicle.trust_score}/100")
        if vehicle.risk_level:
            context_parts.append(f"Risk Seviyesi: {vehicle.risk_level}")
        if vehicle.analysis_summary:
            context_parts.append(f"Analiz Özeti: {vehicle.analysis_summary}")
            
        if vehicle.findings:
            findings_text = "\\n".join(f"- {f}" for f in vehicle.findings)
            context_parts.append(f"Bulgular:\\n{findings_text}")
            
        context_text = "\\n".join(context_parts)
        
        try:
            return COPILOT_CONTEXT_TEMPLATE.format(context=context_text)
        except Exception:
            return f"Aşağıdaki araç bağlamını göz önünde bulundur:\\n{context_text}"

    async def chat(self, request: CopilotRequest) -> CopilotResponse:
        """
        Processes a chat request and returns the assistant's response.
        """
        messages: list[ChatMessage] = [
            ChatMessage(role=ChatRole.SYSTEM, content=COPILOT_SYSTEM_PROMPT)
        ]
        
        vehicle_context_text = self._build_context(request.vehicle)
        messages.append(ChatMessage(role=ChatRole.USER, content=vehicle_context_text))
        
        history = request.history[-self.max_history:] if request.history else []
        for entry in history:
            role = ChatRole.USER if entry.role == 'user' else ChatRole.ASSISTANT
            messages.append(ChatMessage(role=role, content=entry.content))
            
        messages.append(ChatMessage(role=ChatRole.USER, content=request.message))
        
        logger.info("copilot.chat_requested", messages_count=len(messages))
        
        completion = await self.model.complete(messages)
        
        return CopilotResponse(
            reply=completion.content,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens
        )
        
    @property
    def is_available(self) -> bool:
        """Checks if the service is ready to handle requests."""
        return self.model is not None
