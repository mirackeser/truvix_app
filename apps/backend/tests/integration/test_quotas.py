"""Integration tests for per-account consumption ceilings.

These cover a vulnerability rather than a feature. Without a ceiling, one
authenticated account can run analyses in a loop — each costing a vision call
over several images and a reasoning call — and fill the disk with uploads. No
exploit is needed, only patience.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from truvix.modules.users.models import SubscriptionTier, User
from truvix.shared.container import ApplicationContainer

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
VEHICLES_URL = "/api/v1/vehicles"
ANALYSES_URL = "/api/v1/analyses"

_HTTP_CREATED = 201
_HTTP_OK = 200
_HTTP_TOO_MANY = 429

_PASSWORD = "a-sufficiently-long-passphrase"


async def _sign_up(client: AsyncClient, email: str) -> dict[str, str]:
    """Register an account and return its Authorization header."""
    response = await client.post(
        REGISTER_URL,
        json={"email": email, "password": _PASSWORD, "full_name": "Test Kullanici"},
    )
    assert response.status_code == _HTTP_CREATED, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


def _vehicle_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "make": "BMW",
        "model": "320i",
        "model_year": 2021,
        "mileage_km": 67000,
        "fuel_type": "petrol",
        "transmission": "automatic",
        "asking_price": "1250000.00",
    }
    payload.update(overrides)
    return payload


async def _save_vehicle(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(VEHICLES_URL, json=_vehicle_payload(), headers=headers)
    assert response.status_code == _HTTP_CREATED, response.text
    vehicle_id: str = response.json()["id"]
    return vehicle_id


async def _run_analysis(client: AsyncClient, headers: dict[str, str], vehicle_id: str):
    """Open and start an analysis, returning the start response."""
    opened = await client.post(ANALYSES_URL, data={"vehicle_id": vehicle_id}, headers=headers)
    assert opened.status_code == _HTTP_CREATED, opened.text
    return await client.post(f"{ANALYSES_URL}/{opened.json()['id']}/start", headers=headers)


async def _make_premium(container: ApplicationContainer, email: str) -> None:
    """Promote an account, standing in for a completed subscription."""
    async with container.database.transaction() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        user.subscription_tier = SubscriptionTier.PREMIUM


@pytest.fixture
async def owner(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "owner@truvix.app")


class TestAnalysisAllowance:
    async def test_the_daily_allowance_can_be_spent_in_full(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        allowance = container.settings.quota.free_analyses_per_day
        vehicle_id = await _save_vehicle(client, owner)

        for _ in range(allowance):
            response = await _run_analysis(client, owner, vehicle_id)
            assert response.status_code == _HTTP_OK, response.text

    async def test_one_past_the_allowance_is_refused(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        allowance = container.settings.quota.free_analyses_per_day
        vehicle_id = await _save_vehicle(client, owner)
        for _ in range(allowance):
            await _run_analysis(client, owner, vehicle_id)

        response = await _run_analysis(client, owner, vehicle_id)

        assert response.status_code == _HTTP_TOO_MANY
        assert response.json()["code"] == "quota_exceeded"

    async def test_the_refusal_says_when_the_allowance_renews(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        allowance = container.settings.quota.free_analyses_per_day
        vehicle_id = await _save_vehicle(client, owner)
        for _ in range(allowance + 1):
            response = await _run_analysis(client, owner, vehicle_id)

        # A daily allowance renews on a clock, so the client can say when
        # rather than only that it cannot.
        assert int(response.headers["retry-after"]) > 0

    async def test_a_refusal_is_distinguishable_from_a_rate_limit(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        # Both are 429, but the codes differ so a client can offer an upgrade
        # rather than telling somebody to wait a moment and try again.
        allowance = container.settings.quota.free_analyses_per_day
        vehicle_id = await _save_vehicle(client, owner)
        for _ in range(allowance + 1):
            response = await _run_analysis(client, owner, vehicle_id)

        assert response.json()["code"] != "rate_limit_exceeded"

    async def test_one_account_cannot_spend_another_allowance(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        allowance = container.settings.quota.free_analyses_per_day
        first = await _sign_up(client, "first@truvix.app")
        second = await _sign_up(client, "second@truvix.app")

        first_vehicle = await _save_vehicle(client, first)
        for _ in range(allowance):
            await _run_analysis(client, first, first_vehicle)

        second_vehicle = await _save_vehicle(client, second)
        response = await _run_analysis(client, second, second_vehicle)

        assert response.status_code == _HTTP_OK

    async def test_premium_gets_a_larger_allowance(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        headers = await _sign_up(client, "premium@truvix.app")
        await _make_premium(container, "premium@truvix.app")
        free_allowance = container.settings.quota.free_analyses_per_day
        vehicle_id = await _save_vehicle(client, headers)

        for _ in range(free_allowance + 1):
            response = await _run_analysis(client, headers, vehicle_id)

        # The tier is the whole reason the ceiling is per-account rather than
        # global; a premium account must clear the free ceiling.
        assert response.status_code == _HTTP_OK


class TestGarageCeiling:
    async def test_the_garage_fills_to_its_ceiling(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        ceiling = container.settings.quota.free_vehicles

        for _ in range(ceiling):
            response = await client.post(VEHICLES_URL, json=_vehicle_payload(), headers=owner)
            assert response.status_code == _HTTP_CREATED, response.text

    async def test_one_past_the_ceiling_is_refused(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        ceiling = container.settings.quota.free_vehicles
        for _ in range(ceiling):
            await client.post(VEHICLES_URL, json=_vehicle_payload(), headers=owner)

        response = await client.post(VEHICLES_URL, json=_vehicle_payload(), headers=owner)

        assert response.status_code == _HTTP_TOO_MANY
        assert response.json()["code"] == "quota_exceeded"

    async def test_the_refusal_omits_a_retry_time(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        # A full garage does not empty itself on a clock, so promising a time
        # to retry would be a lie; the user has to make room.
        ceiling = container.settings.quota.free_vehicles
        for _ in range(ceiling + 1):
            response = await client.post(VEHICLES_URL, json=_vehicle_payload(), headers=owner)

        assert "retry-after" not in response.headers

    async def test_removing_a_vehicle_frees_a_slot(
        self, client: AsyncClient, owner: dict[str, str], container: ApplicationContainer
    ) -> None:
        ceiling = container.settings.quota.free_vehicles
        identifiers = []
        for _ in range(ceiling):
            response = await client.post(VEHICLES_URL, json=_vehicle_payload(), headers=owner)
            identifiers.append(response.json()["id"])

        await client.delete(f"{VEHICLES_URL}/{identifiers[0]}", headers=owner)
        response = await client.post(VEHICLES_URL, json=_vehicle_payload(), headers=owner)

        assert response.status_code == _HTTP_CREATED

    async def test_premium_gets_a_larger_garage(
        self, client: AsyncClient, container: ApplicationContainer
    ) -> None:
        headers = await _sign_up(client, "premium-garage@truvix.app")
        await _make_premium(container, "premium-garage@truvix.app")
        free_ceiling = container.settings.quota.free_vehicles

        for _ in range(free_ceiling + 1):
            response = await client.post(VEHICLES_URL, json=_vehicle_payload(), headers=headers)

        assert response.status_code == _HTTP_CREATED
