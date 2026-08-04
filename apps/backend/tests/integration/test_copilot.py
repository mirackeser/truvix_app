"""Integration tests for the copilot conversation flow."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from truvix.shared.ai import ChatCompletion, ChatMessage
from truvix.shared.container import ApplicationContainer
from truvix.shared.errors import ExternalServiceError

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
VEHICLES_URL = "/api/v1/vehicles"
ANALYSES_URL = "/api/v1/analyses"
CONVERSATIONS_URL = "/api/v1/copilot/conversations"
STATUS_URL = "/api/v1/copilot/status"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NOT_FOUND = 404
_HTTP_BAD_GATEWAY = 502
_HTTP_UNAVAILABLE = 503

_PASSWORD = "a-sufficiently-long-passphrase"


class RecordingChatModel:
    """A deterministic model that records everything it is asked."""

    def __init__(self, reply: str = "Bu araç verilere göre alınabilir görünüyor.") -> None:
        self.reply = reply
        self.received: list[list[ChatMessage]] = []

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        json_response: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatCompletion:
        self.received.append(messages)
        return ChatCompletion(content=self.reply, input_tokens=50, output_tokens=25)


class OutageChatModel:
    """A model whose provider always fails."""

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        json_response: bool = False,
        max_output_tokens: int | None = None,
    ) -> ChatCompletion:
        raise ExternalServiceError("provider down", service="openai")


async def _sign_up(client: AsyncClient, email: str) -> dict[str, str]:
    """Register an account and return its Authorization header."""
    response = await client.post(
        REGISTER_URL,
        json={"email": email, "password": _PASSWORD, "full_name": "Test Kullanici"},
    )
    assert response.status_code == _HTTP_CREATED, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


async def _save_vehicle(client: AsyncClient, headers: dict[str, str], **overrides: Any) -> str:
    """Save a vehicle and return its id."""
    payload: dict[str, Any] = {
        "make": "BMW",
        "model": "320i",
        "variant": "M Sport",
        "model_year": 2021,
        "mileage_km": 67000,
        "fuel_type": "petrol",
        "transmission": "automatic",
        "asking_price": "1250000.00",
        "plate": "34 ABC 123",
        "vin": "WVWZZZ1JZXW000001",
    }
    payload.update(overrides)
    response = await client.post(VEHICLES_URL, json=payload, headers=headers)
    assert response.status_code == _HTTP_CREATED, response.text
    vehicle_id: str = response.json()["id"]
    return vehicle_id


async def _open_conversation(client: AsyncClient, headers: dict[str, str], vehicle_id: str) -> str:
    """Open a conversation and return its id."""
    response = await client.post(
        CONVERSATIONS_URL, json={"vehicle_id": vehicle_id}, headers=headers
    )
    assert response.status_code == _HTTP_CREATED, response.text
    conversation_id: str = response.json()["conversation"]["id"]
    return conversation_id


@pytest.fixture
async def owner(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "owner@truvix.app")


@pytest.fixture
async def intruder(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "intruder@truvix.app")


@pytest.fixture
def chat_model(container: ApplicationContainer) -> RecordingChatModel:
    """Install a deterministic chat model into the running container."""
    model = RecordingChatModel()
    container.chat_model = model
    return model


class TestAvailability:
    async def test_reports_unavailable_without_a_model(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        response = await client.get(STATUS_URL, headers=owner)

        assert response.json() == {"available": False}

    async def test_reports_available_with_a_model(
        self, client: AsyncClient, owner: dict[str, str], chat_model: RecordingChatModel
    ) -> None:
        response = await client.get(STATUS_URL, headers=owner)

        assert response.json() == {"available": True}

    async def test_sending_without_a_model_returns_service_unavailable(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)

        response = await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "Bu araç alınır mı?"},
            headers=owner,
        )

        assert response.status_code == _HTTP_UNAVAILABLE
        assert response.json()["code"] == "service_unavailable"


class TestConversations:
    async def test_opening_twice_returns_the_same_thread(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)

        first = await _open_conversation(client, owner, vehicle_id)
        second = await _open_conversation(client, owner, vehicle_id)

        assert first == second

    async def test_cannot_open_about_another_accounts_vehicle(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)

        response = await client.post(
            CONVERSATIONS_URL, json={"vehicle_id": vehicle_id}, headers=intruder
        )

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_another_account_cannot_read_the_thread(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)

        response = await client.get(f"{CONVERSATIONS_URL}/{conversation_id}", headers=intruder)

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_listing_shows_only_own_conversations(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        own_vehicle = await _save_vehicle(client, owner)
        other_vehicle = await _save_vehicle(
            client, intruder, plate="06 XYZ 456", vin="WVWZZZ1JZXW000002"
        )
        await _open_conversation(client, owner, own_vehicle)
        await _open_conversation(client, intruder, other_vehicle)

        response = await client.get(CONVERSATIONS_URL, headers=owner)

        assert response.json()["total"] == 1


class TestMessaging:
    async def test_a_message_returns_and_persists_the_exchange(
        self, client: AsyncClient, owner: dict[str, str], chat_model: RecordingChatModel
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)

        response = await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "Bu araç alınır mı?"},
            headers=owner,
        )

        body = response.json()
        assert response.status_code == _HTTP_CREATED
        assert body["user_message"]["content"] == "Bu araç alınır mı?"
        assert body["assistant_message"]["role"] == "assistant"
        assert body["assistant_message"]["content"] == chat_model.reply

        history = await client.get(f"{CONVERSATIONS_URL}/{conversation_id}", headers=owner)
        assert len(history.json()["messages"]) == 2

    async def test_the_vehicle_context_reaches_the_model(
        self, client: AsyncClient, owner: dict[str, str], chat_model: RecordingChatModel
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)

        await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "Gerçek değeri nedir?"},
            headers=owner,
        )

        sent = " ".join(message.content for message in chat_model.received[0])
        assert "BMW 320i M Sport" in sent
        assert "67.000 km" in sent

    async def test_plate_and_vin_never_reach_the_model(
        self, client: AsyncClient, owner: dict[str, str], chat_model: RecordingChatModel
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)

        await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "Bu araç neden riskli?"},
            headers=owner,
        )

        sent = " ".join(message.content for message in chat_model.received[0])
        assert "34ABC123" not in sent
        assert "WVWZZZ1JZXW000001" not in sent

    async def test_the_latest_completed_report_is_in_context(
        self, client: AsyncClient, owner: dict[str, str], chat_model: RecordingChatModel
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        analysis = await client.post(ANALYSES_URL, data={"vehicle_id": vehicle_id}, headers=owner)
        analysis_id = analysis.json()["id"]
        await client.post(f"{ANALYSES_URL}/{analysis_id}/start", headers=owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)

        await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "Analiz sonucuna göre ne düşünüyorsun?"},
            headers=owner,
        )

        sent = " ".join(message.content for message in chat_model.received[-1])
        assert "SON ANALİZ RAPORU" in sent
        assert "Güven skoru" in sent

    async def test_history_is_replayed_on_the_next_message(
        self, client: AsyncClient, owner: dict[str, str], chat_model: RecordingChatModel
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)
        await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "İlk sorum bu."},
            headers=owner,
        )

        await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "İkinci sorum bu."},
            headers=owner,
        )

        replayed = " ".join(message.content for message in chat_model.received[1])
        assert "İlk sorum bu." in replayed

    async def test_a_provider_outage_persists_nothing(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        container.chat_model = OutageChatModel()
        vehicle_id = await _save_vehicle(client, owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)

        response = await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "Bu soru kaybolmamalı ama kaydedilmemeli."},
            headers=owner,
        )

        assert response.status_code == _HTTP_BAD_GATEWAY
        history = await client.get(f"{CONVERSATIONS_URL}/{conversation_id}", headers=owner)
        assert history.json()["messages"] == []

    async def test_another_account_cannot_send_into_the_thread(
        self,
        client: AsyncClient,
        owner: dict[str, str],
        intruder: dict[str, str],
        chat_model: RecordingChatModel,
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        conversation_id = await _open_conversation(client, owner, vehicle_id)

        response = await client.post(
            f"{CONVERSATIONS_URL}/{conversation_id}/messages",
            json={"content": "Ben baskasiyim."},
            headers=intruder,
        )

        assert response.status_code == _HTTP_NOT_FOUND
