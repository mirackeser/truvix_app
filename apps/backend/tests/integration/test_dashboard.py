"""Integration tests for the home screen aggregate."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
VEHICLES_URL = "/api/v1/vehicles"
ANALYSES_URL = "/api/v1/analyses"
DASHBOARD_URL = "/api/v1/dashboard"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_UNAUTHORIZED = 401

_PASSWORD = "a-sufficiently-long-passphrase"


async def _sign_up(client: AsyncClient, email: str, name: str = "Kerem Yilmaz") -> dict[str, str]:
    """Register an account and return its Authorization header."""
    response = await client.post(
        REGISTER_URL, json={"email": email, "password": _PASSWORD, "full_name": name}
    )
    assert response.status_code == _HTTP_CREATED, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


async def _save_vehicle(client: AsyncClient, headers: dict[str, str], **overrides: Any) -> str:
    """Save a vehicle and return its id."""
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
    response = await client.post(VEHICLES_URL, json=payload, headers=headers)
    assert response.status_code == _HTTP_CREATED, response.text
    vehicle_id: str = response.json()["id"]
    return vehicle_id


@pytest.fixture
async def owner(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "owner@truvix.app")


@pytest.fixture
async def intruder(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "intruder@truvix.app", name="Baska Kisi")


class TestEmptyDashboard:
    async def test_a_new_account_gets_a_complete_empty_payload(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        response = await client.get(DASHBOARD_URL, headers=owner)

        body = response.json()
        assert response.status_code == _HTTP_OK
        assert body["user"]["full_name"] == "Kerem Yilmaz"
        assert body["user"]["is_premium"] is False
        assert body["garage"]["total"] == 0
        assert body["unread_notifications"] == 0
        assert body["recent_analyses"] == []
        assert body["price_drops"] == []
        assert body["saved_vehicles"] == []
        assert body["recommendations"] == []

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(DASHBOARD_URL)

        assert response.status_code == _HTTP_UNAUTHORIZED


class TestPopulatedDashboard:
    async def test_every_section_is_filled(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        favourite = await _save_vehicle(client, owner)
        await client.patch(
            f"{VEHICLES_URL}/{favourite}", json={"is_favourite": True}, headers=owner
        )
        await client.post(
            f"{VEHICLES_URL}/{favourite}/prices", json={"price": "1225000.00"}, headers=owner
        )
        opened = await client.post(ANALYSES_URL, data={"vehicle_id": favourite}, headers=owner)
        await client.post(f"{ANALYSES_URL}/{opened.json()['id']}/start", headers=owner)

        response = await client.get(DASHBOARD_URL, headers=owner)

        body = response.json()
        assert body["garage"]["total"] == 1
        assert body["garage"]["favourites"] == 1
        assert len(body["saved_vehicles"]) == 1
        assert len(body["price_drops"]) == 1
        assert len(body["recent_analyses"]) == 1
        assert len(body["recommendations"]) == 1
        assert body["unread_notifications"] > 0

    async def test_price_drop_cards_carry_their_trend(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await client.post(
            f"{VEHICLES_URL}/{vehicle_id}/prices", json={"price": "1225000.00"}, headers=owner
        )

        response = await client.get(DASHBOARD_URL, headers=owner)

        trend = response.json()["price_drops"][0]["price_trend"]
        assert trend["absolute_change"].startswith("-")

    async def test_recommendations_are_ordered_by_score(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        strong = await _save_vehicle(client, owner, vin="WVWZZZ1JZXW000001")
        weak = await _save_vehicle(client, owner, model_year=2000, mileage_km=900000)
        for vehicle_id in (weak, strong):
            opened = await client.post(ANALYSES_URL, data={"vehicle_id": vehicle_id}, headers=owner)
            await client.post(f"{ANALYSES_URL}/{opened.json()['id']}/start", headers=owner)

        response = await client.get(DASHBOARD_URL, headers=owner)

        scores = [item["trust_score"] for item in response.json()["recommendations"]]
        assert scores == sorted(scores, reverse=True)

    async def test_sections_are_bounded(self, client: AsyncClient, owner: dict[str, str]) -> None:
        for index in range(7):
            vehicle_id = await _save_vehicle(client, owner, plate=f"34 AB {100 + index}")
            await client.post(
                f"{VEHICLES_URL}/{vehicle_id}/prices",
                json={"price": "1000000.00"},
                headers=owner,
            )

        response = await client.get(DASHBOARD_URL, headers=owner)

        body = response.json()
        assert body["garage"]["total"] == 7
        assert len(body["price_drops"]) == 5


class TestIsolation:
    async def test_one_account_never_sees_another_dashboard(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await client.patch(
            f"{VEHICLES_URL}/{vehicle_id}", json={"is_favourite": True}, headers=owner
        )

        response = await client.get(DASHBOARD_URL, headers=intruder)

        body = response.json()
        assert body["user"]["full_name"] == "Baska Kisi"
        assert body["garage"]["total"] == 0
        assert body["saved_vehicles"] == []
