"""Integration tests for device registration and push delivery.

Apple is stood in for by a recording sender, so these check what the
application does with a device token rather than whether Apple accepts one:
that a device belongs to exactly one account, that a notification reaches every
device the account has, and that a token Apple rejects is thrown away instead of
being retried forever.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from truvix.main import create_app
from truvix.modules.notifications.devices import DeviceRegistry
from truvix.modules.notifications.models import DeviceToken
from truvix.modules.notifications.router import get_device_registry
from truvix.modules.users.models import User
from truvix.shared.config import Settings
from truvix.shared.container import ApplicationContainer
from truvix.shared.dependencies import SessionDep
from truvix.shared.push import DeliveryOutcome, PushMessage

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
VEHICLES_URL = "/api/v1/vehicles"
DEVICES_URL = "/api/v1/notifications/devices"
NOTIFICATIONS_URL = "/api/v1/notifications"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NO_CONTENT = 204
_HTTP_UNAUTHORIZED = 401
_HTTP_UNPROCESSABLE = 422

_PASSWORD = "a-sufficiently-long-passphrase"
# APNs tokens are 64 hex characters; the schema's floor is 32.
_TOKEN_A = "a" * 64
_TOKEN_B = "b" * 64


class RecordingSender:
    """Stands in for Apple, recording what it was asked to deliver."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, PushMessage]] = []
        #: Tokens to answer as dead, the way Apple reports a deleted app.
        self.rejected: set[str] = set()

    async def send(self, message: PushMessage, *, device_token: str) -> DeliveryOutcome:
        """Record the notification and report the configured outcome."""
        self.sent.append((device_token, message))
        if device_token in self.rejected:
            return DeliveryOutcome.UNREGISTERED
        return DeliveryOutcome.DELIVERED

    @property
    def tokens(self) -> list[str]:
        """Every token sent to, in order."""
        return [token for token, _ in self.sent]


@pytest.fixture
def sender() -> RecordingSender:
    """A push sender that records rather than delivers."""
    return RecordingSender()


@pytest.fixture
async def client(
    settings: Settings, container: ApplicationContainer, sender: RecordingSender
) -> Any:
    """A client whose pushes go into the recording sender.

    The sender is substituted in two places because notifications arrive by two
    routes: endpoints resolve the registry through dependency injection, while
    event handlers read it off the session.
    """
    app = create_app(settings)
    app.state.container = container

    def override(session: SessionDep) -> DeviceRegistry:
        return DeviceRegistry(session, sender)

    app.dependency_overrides[get_device_registry] = override

    original = container.push_sender
    container._push_sender = sender  # the seam handlers read from
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
            yield http_client
    finally:
        container._push_sender = original


async def _register(client: AsyncClient, email: str) -> dict[str, str]:
    """Register an account and return its Authorization header."""
    response = await client.post(
        REGISTER_URL,
        json={"email": email, "password": _PASSWORD, "full_name": "Bildirim Kullanici"},
    )
    assert response.status_code == _HTTP_CREATED, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


async def _add_device(client: AsyncClient, headers: dict[str, str], token: str) -> None:
    """Register a device for an account."""
    response = await client.put(DEVICES_URL, json={"token": token}, headers=headers)
    assert response.status_code == _HTTP_OK, response.text


async def _drop_price(client: AsyncClient, headers: dict[str, str]) -> None:
    """Save a vehicle and record a lower price, which raises a notification."""
    vehicle = await client.post(
        VEHICLES_URL,
        json={
            "make": "BMW",
            "model": "320i",
            "model_year": 2021,
            "mileage_km": 67000,
            "fuel_type": "petrol",
            "transmission": "automatic",
            "asking_price": "1250000.00",
        },
        headers=headers,
    )
    assert vehicle.status_code == _HTTP_CREATED, vehicle.text
    dropped = await client.post(
        f"{VEHICLES_URL}/{vehicle.json()['id']}/prices",
        json={"price": "1200000.00"},
        headers=headers,
    )
    assert dropped.status_code in {_HTTP_OK, _HTTP_CREATED}, dropped.text


class TestRegistering:
    """A device belongs to exactly one account."""

    async def test_a_device_can_be_registered(self, client: AsyncClient, session: Any) -> None:
        headers = await _register(client, "device-owner@truvix.app")

        response = await client.put(DEVICES_URL, json={"token": _TOKEN_A}, headers=headers)

        assert response.status_code == _HTTP_OK, response.text
        stored = await session.scalar(select(DeviceToken).where(DeviceToken.token == _TOKEN_A))
        assert stored is not None

    async def test_the_token_is_not_echoed_back(self, client: AsyncClient) -> None:
        """Nothing needs it returned, and a value not sent cannot leak."""
        headers = await _register(client, "no-echo@truvix.app")

        response = await client.put(DEVICES_URL, json={"token": _TOKEN_A}, headers=headers)

        assert _TOKEN_A not in response.text

    async def test_registering_twice_does_not_duplicate(
        self, client: AsyncClient, session: Any
    ) -> None:
        """The app registers on every launch; iOS reissues tokens at will."""
        headers = await _register(client, "repeat@truvix.app")

        await _add_device(client, headers, _TOKEN_A)
        await _add_device(client, headers, _TOKEN_A)

        count = await session.scalar(
            select(func.count()).select_from(DeviceToken).where(DeviceToken.token == _TOKEN_A)
        )
        assert count == 1

    async def test_a_device_moves_to_whoever_signs_in(
        self, client: AsyncClient, session: Any
    ) -> None:
        """Otherwise the previous occupant keeps getting a stranger's alerts."""
        first = await _register(client, "first-occupant@truvix.app")
        await _add_device(client, first, _TOKEN_A)

        second = await _register(client, "second-occupant@truvix.app")
        await _add_device(client, second, _TOKEN_A)

        stored = await session.scalar(select(DeviceToken).where(DeviceToken.token == _TOKEN_A))
        owner = await session.scalar(select(User).where(User.email == "second-occupant@truvix.app"))
        assert stored is not None
        assert owner is not None
        assert stored.user_id == owner.id

    async def test_unregistering_stops_notifications(
        self, client: AsyncClient, session: Any
    ) -> None:
        headers = await _register(client, "signs-out@truvix.app")
        await _add_device(client, headers, _TOKEN_A)

        response = await client.request(
            "DELETE", DEVICES_URL, json={"token": _TOKEN_A}, headers=headers
        )

        assert response.status_code == _HTTP_NO_CONTENT
        remaining = await session.scalar(select(DeviceToken).where(DeviceToken.token == _TOKEN_A))
        assert remaining is None

    async def test_registering_requires_signing_in(self, client: AsyncClient) -> None:
        response = await client.put(DEVICES_URL, json={"token": _TOKEN_A})

        assert response.status_code == _HTTP_UNAUTHORIZED

    async def test_a_token_too_short_to_be_real_is_refused(self, client: AsyncClient) -> None:
        headers = await _register(client, "short-token@truvix.app")

        response = await client.put(DEVICES_URL, json={"token": "abc"}, headers=headers)

        assert response.status_code == _HTTP_UNPROCESSABLE

    async def test_deleting_an_account_takes_its_devices_with_it(
        self, client: AsyncClient, session: Any
    ) -> None:
        headers = await _register(client, "device-cascade@truvix.app")
        await _add_device(client, headers, _TOKEN_A)

        user = await session.scalar(select(User).where(User.email == "device-cascade@truvix.app"))
        assert user is not None
        await session.delete(user)
        await session.flush()

        remaining = await session.scalar(select(DeviceToken).where(DeviceToken.token == _TOKEN_A))
        assert remaining is None


class TestDelivering:
    """A notification should reach the phone, not only the list."""

    async def test_a_price_drop_reaches_the_device(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        headers = await _register(client, "gets-pushed@truvix.app")
        await _add_device(client, headers, _TOKEN_A)

        await _drop_price(client, headers)

        assert _TOKEN_A in sender.tokens
        _, message = sender.sent[-1]
        assert "düştü" in message.title.lower() or "düştü" in message.body.lower()

    async def test_every_device_the_account_has_is_reached(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """Somebody with a phone and an iPad should hear it on both."""
        headers = await _register(client, "two-devices@truvix.app")
        await _add_device(client, headers, _TOKEN_A)
        await _add_device(client, headers, _TOKEN_B)

        await _drop_price(client, headers)

        assert set(sender.tokens) == {_TOKEN_A, _TOKEN_B}

    async def test_the_badge_carries_the_unread_count(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        headers = await _register(client, "badge@truvix.app")
        await _add_device(client, headers, _TOKEN_A)

        await _drop_price(client, headers)

        _, message = sender.sent[-1]
        assert message.badge is not None
        assert message.badge > 0

    async def test_the_notification_carries_its_vehicle(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """A tap has to be able to open the vehicle it is about."""
        headers = await _register(client, "deep-link@truvix.app")
        await _add_device(client, headers, _TOKEN_A)

        await _drop_price(client, headers)

        _, message = sender.sent[-1]
        assert message.data is not None
        assert "vehicle_id" in message.data
        assert message.data["event_type"] == "price_drop"

    async def test_an_account_with_no_device_is_not_a_failure(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        """Somebody who declined notifications still gets the price drop."""
        headers = await _register(client, "no-device@truvix.app")

        await _drop_price(client, headers)

        assert sender.sent == []
        listed = await client.get(NOTIFICATIONS_URL, headers=headers)
        assert listed.json()["total"] >= 1

    async def test_another_accounts_device_is_not_sent_to(
        self, client: AsyncClient, sender: RecordingSender
    ) -> None:
        bystander = await _register(client, "bystander-device@truvix.app")
        await _add_device(client, bystander, _TOKEN_B)

        owner = await _register(client, "owner-device@truvix.app")
        await _add_device(client, owner, _TOKEN_A)
        await _drop_price(client, owner)

        assert _TOKEN_B not in sender.tokens


class TestDeadTokens:
    """A token Apple rejects should not be retried forever."""

    async def test_a_rejected_token_is_forgotten(
        self, client: AsyncClient, sender: RecordingSender, session: Any
    ) -> None:
        headers = await _register(client, "dead-token@truvix.app")
        await _add_device(client, headers, _TOKEN_A)
        sender.rejected.add(_TOKEN_A)

        await _drop_price(client, headers)

        remaining = await session.scalar(select(DeviceToken).where(DeviceToken.token == _TOKEN_A))
        assert remaining is None

    async def test_a_rejected_token_does_not_take_the_others_with_it(
        self, client: AsyncClient, sender: RecordingSender, session: Any
    ) -> None:
        headers = await _register(client, "one-dead@truvix.app")
        await _add_device(client, headers, _TOKEN_A)
        await _add_device(client, headers, _TOKEN_B)
        sender.rejected.add(_TOKEN_A)

        await _drop_price(client, headers)

        assert _TOKEN_B in sender.tokens
        survivor = await session.scalar(select(DeviceToken).where(DeviceToken.token == _TOKEN_B))
        assert survivor is not None
