"""Copilot business logic: context assembly and conversation flow.

The copilot answers about one specific vehicle with that vehicle's data and its
latest completed analysis in context. The model never sees the plate or VIN
value, and the caller's message is capped in length before it is sent anywhere.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from truvix.modules.analysis.models import VehicleAnalysis
from truvix.modules.analysis.repository import AnalysisRepository
from truvix.modules.copilot.models import CopilotConversation, CopilotMessage, MessageRole
from truvix.modules.copilot.repository import CopilotRepository
from truvix.modules.vehicles.models import Vehicle
from truvix.modules.vehicles.repository import VehicleRepository
from truvix.shared.ai import ChatMessage, ChatModel, ChatRole
from truvix.shared.config import AISettings
from truvix.shared.errors import NotFoundError, ServiceUnavailableError
from truvix.shared.logging import get_logger
from truvix.shared.pagination import PageParams

_logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "Sen Truvix AI Copilot'sun: ikinci el araç alımında kullanıcıya yardımcı "
    "olan uzman bir danışmansın. Sana kullanıcının incelediği aracın verileri "
    "ve varsa son analiz raporu verildi.\n\n"
    "Kurallar:\n"
    "- Türkçe, net ve saygılı yanıt ver; gereksiz uzatma.\n"
    "- Yalnızca sana verilen araç verisine ve genel otomotiv bilgisine dayan; "
    "bilmediğin bir şeyi uydurma, emin değilsen belirt.\n"
    "- Fiyat tahmini istenirse verideki fiyat ve analiz bulgularıyla "
    "gerekçelendir; kesin piyasa değeri veremeyeceğini söyle.\n"
    "- Ekspertiz gerektiren konularda mutlaka fiziksel ekspertiz öner."
)


def _vehicle_context(vehicle: Vehicle, analysis: VehicleAnalysis | None) -> str:
    """Render the vehicle and its latest report as model context.

    The plate and VIN values are deliberately omitted; their presence is
    signalled as a boolean where it matters to the answer.
    """
    lines = [
        "ARAÇ BİLGİLERİ:",
        f"- Araç: {vehicle.display_name} ({vehicle.model_year})",
        f"- Kilometre: {vehicle.mileage_km:,} km",
        f"- Yakıt/Vites: {vehicle.fuel_type.value} / {vehicle.transmission.value}",
        f"- İstenen fiyat: {vehicle.asking_price} {vehicle.currency.value}",
        f"- Şehir: {vehicle.city or 'belirtilmemiş'}",
        f"- VIN kayıtlı mı: {'evet' if vehicle.vin else 'hayır'}",
    ]
    if analysis is not None:
        lines += [
            "",
            "SON ANALİZ RAPORU:",
            f"- Güven skoru: {analysis.trust_score}/100 "
            f"({analysis.risk_level.value if analysis.risk_level else 'bilinmiyor'})",
            f"- Özet: {analysis.summary or '-'}",
            "- Bulgular:",
            *[
                f"  * [{finding.severity.value}] {finding.title}: {finding.detail}"
                for finding in analysis.findings
            ],
        ]
    else:
        lines += ["", "Bu araç için tamamlanmış bir analiz raporu yok."]
    return "\n".join(lines)


class CopilotService:
    """Manages copilot conversations and produces assistant replies."""

    def __init__(
        self,
        *,
        conversations: CopilotRepository,
        vehicles: VehicleRepository,
        analyses: AnalysisRepository,
        model: ChatModel | None,
        settings: AISettings,
    ) -> None:
        """Initialise the service.

        Args:
            conversations: Access to conversation records.
            vehicles: Access to vehicle records, for ownership checks.
            analyses: Access to analysis records, for report context.
            model: The chat model, or ``None`` when AI is not configured.
            settings: History window and model limits.
        """
        self._conversations = conversations
        self._vehicles = vehicles
        self._analyses = analyses
        self._model = model
        self._settings = settings

    async def open_conversation(
        self, *, owner_id: uuid.UUID, vehicle_id: uuid.UUID
    ) -> CopilotConversation:
        """Return the owner's conversation for a vehicle, creating it if new.

        Get-or-create keeps one thread per vehicle, matching the screen: the
        copilot opens on a car and its history is always there.

        Args:
            owner_id: The account opening the conversation.
            vehicle_id: The vehicle to talk about.

        Raises:
            NotFoundError: If the vehicle is not the owner's.
        """
        vehicle = await self._vehicles.get_for_owner(owner_id=owner_id, vehicle_id=vehicle_id)
        if vehicle is None:
            raise NotFoundError.for_resource("Vehicle", vehicle_id)

        existing = await self._conversations.find_for_vehicle(
            owner_id=owner_id, vehicle_id=vehicle.id
        )
        if existing is not None:
            return existing

        conversation = CopilotConversation(user_id=owner_id, vehicle_id=vehicle.id)
        self._conversations.add(conversation)
        await self._conversations.flush()
        _logger.info("copilot_conversation_opened", conversation_id=str(conversation.id))
        return await self._require(owner_id=owner_id, conversation_id=conversation.id)

    async def get_conversation(
        self, *, owner_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> tuple[CopilotConversation, Sequence[CopilotMessage]]:
        """Fetch one of the owner's conversations with its full history.

        Args:
            owner_id: The account the conversation must belong to.
            conversation_id: The conversation to fetch.

        Raises:
            NotFoundError: If the conversation is not the owner's.
        """
        conversation = await self._require(owner_id=owner_id, conversation_id=conversation_id)
        messages = await self._conversations.all_messages(conversation_id=conversation.id)
        return conversation, messages

    async def list_conversations(
        self, *, owner_id: uuid.UUID, params: PageParams
    ) -> tuple[Sequence[CopilotConversation], int]:
        """List a page of the owner's conversations.

        Args:
            owner_id: The account whose conversations to list.
            params: Pagination parameters.
        """
        return await self._conversations.list_for_owner(owner_id=owner_id, params=params)

    async def send_message(
        self, *, owner_id: uuid.UUID, conversation_id: uuid.UUID, content: str
    ) -> tuple[CopilotMessage, CopilotMessage]:
        """Send a user message and return it with the assistant's reply.

        Nothing is persisted unless the model produces a reply, so a provider
        outage cannot leave a question hanging unanswered in the history and
        a retry cannot duplicate it.

        Args:
            owner_id: The account the conversation must belong to.
            conversation_id: The conversation to continue.
            content: The user's message, already length-validated.

        Returns:
            The stored user message and the stored assistant reply.

        Raises:
            NotFoundError: If the conversation is not the owner's.
            ServiceUnavailableError: If AI is not configured.
            ExternalServiceError: If the provider fails to reply.
        """
        if self._model is None:
            raise ServiceUnavailableError("AI assistance is not available on this deployment.")

        conversation = await self._require(owner_id=owner_id, conversation_id=conversation_id)

        latest_analysis = await self._analyses.latest_completed_for_vehicle(
            owner_id=owner_id, vehicle_id=conversation.vehicle_id
        )
        history = await self._conversations.recent_messages(
            conversation_id=conversation.id,
            limit=self._settings.copilot_history_window,
        )

        prompt: list[ChatMessage] = [
            ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT),
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=_vehicle_context(conversation.vehicle, latest_analysis),
            ),
            *[
                ChatMessage(
                    role=ChatRole.USER if message.role is MessageRole.USER else ChatRole.ASSISTANT,
                    content=message.content,
                )
                for message in history
            ],
            ChatMessage(role=ChatRole.USER, content=content),
        ]

        completion = await self._model.complete(prompt)

        user_message = CopilotMessage(
            conversation_id=conversation.id, role=MessageRole.USER, content=content
        )
        assistant_message = CopilotMessage(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=completion.content,
        )
        self._conversations.add_message(user_message)
        self._conversations.add_message(assistant_message)
        await self._conversations.flush()

        _logger.info(
            "copilot_reply_produced",
            conversation_id=str(conversation.id),
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )
        return user_message, assistant_message

    @property
    def is_available(self) -> bool:
        """Whether the copilot can currently answer."""
        return self._model is not None

    async def _require(
        self, *, owner_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> CopilotConversation:
        """Fetch a conversation or raise if it is not the owner's."""
        conversation = await self._conversations.get_for_owner(
            owner_id=owner_id, conversation_id=conversation_id
        )
        if conversation is None:
            raise NotFoundError.for_resource("Conversation", conversation_id)
        return conversation
