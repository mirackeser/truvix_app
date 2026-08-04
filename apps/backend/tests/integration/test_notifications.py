"""Integration tests for the notification centre and its event pipeline."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"
VEHICLES_URL = "/api/v1/vehicles"
ANALYSES_URL = "/api/v1/analyses"
NOTIFICATIONS_URL = "/api/v1/notifications"
SUMMARY_URL = "/api/v1/notifications/summary"
PREFERENCES_URL = "/api/v1/notifications/preferences"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_UNAUTHORIZED = 401
_HTTP_NOT_FOUND = 404

_PASSWORD = "a-sufficiently-long-passphrase"


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
    }
    payload.update(overrides)
    response = await client.post(VEHICLES_URL, json=payload, headers=headers)
    assert response.status_code == _HTTP_CREATED, response.text
    vehicle_id: str = response.json()["id"]
    return vehicle_id


async def _drop_price(
    client: AsyncClient, headers: dict[str, str], vehicle_id: str, price: str
) -> None:
    """Record a lower price for a vehicle."""
    response = await client.post(
        f"{VEHICLES_URL}/{vehicle_id}/prices", json={"price": price}, headers=headers
    )
    assert response.status_code == _HTTP_CREATED, response.text


async def _run_analysis(client: AsyncClient, headers: dict[str, str], vehicle_id: str) -> dict:
    """Open and run an analysis, returning the finished report."""
    opened = await client.post(ANALYSES_URL, data={"vehicle_id": vehicle_id}, headers=headers)
    analysis_id = opened.json()["id"]
    finished = await client.post(f"{ANALYSES_URL}/{analysis_id}/start", headers=headers)
    body: dict = finished.json()
    return body


@pytest.fixture
async def owner(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "owner@truvix.app")


@pytest.fixture
async def intruder(client: AsyncClient) -> dict[str, str]:
    return await _sign_up(client, "intruder@truvix.app")


class TestPriceDropNotifications:
    async def test_a_price_drop_files_an_opportunity(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1225000.00")

        response = await client.get(NOTIFICATIONS_URL, headers=owner)

        body = response.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["category"] == "opportunity"
        assert item["event_type"] == "price_drop"
        assert item["title"] == "Fiyat düştü!"
        assert "25.000 TL" in item["body"]
        assert item["vehicle_id"] == vehicle_id
        assert item["read"] is False

    async def test_a_rising_price_produces_nothing(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1300000.00")

        response = await client.get(NOTIFICATIONS_URL, headers=owner)

        assert response.json()["total"] == 0

    async def test_a_patch_price_drop_also_notifies(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)

        await client.patch(
            f"{VEHICLES_URL}/{vehicle_id}", json={"asking_price": "1200000.00"}, headers=owner
        )

        response = await client.get(NOTIFICATIONS_URL, headers=owner)
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["category"] == "opportunity"

    async def test_disabling_price_changes_suppresses_the_notification(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await client.patch(PREFERENCES_URL, json={"price_changes": False}, headers=owner)

        await _drop_price(client, owner, vehicle_id, "1225000.00")

        response = await client.get(NOTIFICATIONS_URL, headers=owner)
        assert response.json()["total"] == 0


class TestAnalysisNotifications:
    async def test_a_completed_analysis_files_an_ai_suggestion(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        report = await _run_analysis(client, owner, vehicle_id)

        response = await client.get(
            NOTIFICATIONS_URL, params={"category": "ai_suggestion"}, headers=owner
        )

        body = response.json()
        assert body["total"] == 1
        assert str(report["trust_score"]) in body["items"][0]["body"]

    async def test_a_high_risk_report_also_files_a_risk_alert(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        # Old, heavily used, no evidence: the rule engine scores this high risk.
        vehicle_id = await _save_vehicle(client, owner, model_year=2000, mileage_km=900000)
        report = await _run_analysis(client, owner, vehicle_id)
        assert report["risk_level"] == "high"

        risks = await client.get(NOTIFICATIONS_URL, params={"category": "risk"}, headers=owner)

        assert risks.json()["total"] == 1
        assert risks.json()["items"][0]["title"] == "Risk uyarısı"

    async def test_a_low_risk_report_files_no_risk_alert(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner, vin="WVWZZZ1JZXW000001")
        report = await _run_analysis(client, owner, vehicle_id)
        assert report["risk_level"] != "high"

        risks = await client.get(NOTIFICATIONS_URL, params={"category": "risk"}, headers=owner)

        assert risks.json()["total"] == 0

    async def test_disabling_ai_suggestions_suppresses_the_notification(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await client.patch(PREFERENCES_URL, json={"ai_suggestions": False}, headers=owner)

        await _run_analysis(client, owner, vehicle_id)

        response = await client.get(
            NOTIFICATIONS_URL, params={"category": "ai_suggestion"}, headers=owner
        )
        assert response.json()["total"] == 0


class TestSummaryAndFilters:
    async def test_summary_counts_match_the_tabs(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1225000.00")
        await _run_analysis(client, owner, vehicle_id)

        response = await client.get(SUMMARY_URL, headers=owner)

        body = response.json()
        assert body["opportunities"] == 1
        assert body["ai_suggestions"] == 1
        assert body["total"] == body["opportunities"] + body["risks"] + body["ai_suggestions"]
        assert body["unread"] == body["total"]

    async def test_unread_only_filter(self, client: AsyncClient, owner: dict[str, str]) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1225000.00")
        listed = await client.get(NOTIFICATIONS_URL, headers=owner)
        notification_id = listed.json()["items"][0]["id"]
        await client.post(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=owner)

        unread = await client.get(NOTIFICATIONS_URL, params={"unread_only": "true"}, headers=owner)

        assert unread.json()["total"] == 0


class TestReadState:
    async def test_marking_one_read(self, client: AsyncClient, owner: dict[str, str]) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1225000.00")
        listed = await client.get(NOTIFICATIONS_URL, headers=owner)
        notification_id = listed.json()["items"][0]["id"]

        marked = await client.post(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=owner)

        assert marked.json()["read"] is True
        summary = await client.get(SUMMARY_URL, headers=owner)
        assert summary.json()["unread"] == 0

    async def test_mark_all_read(self, client: AsyncClient, owner: dict[str, str]) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1225000.00")
        await _drop_price(client, owner, vehicle_id, "1200000.00")

        response = await client.post(f"{NOTIFICATIONS_URL}/read-all", headers=owner)

        assert response.json()["marked"] == 2
        summary = await client.get(SUMMARY_URL, headers=owner)
        assert summary.json()["unread"] == 0

    async def test_marking_is_idempotent(self, client: AsyncClient, owner: dict[str, str]) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1225000.00")
        listed = await client.get(NOTIFICATIONS_URL, headers=owner)
        notification_id = listed.json()["items"][0]["id"]
        await client.post(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=owner)

        second = await client.post(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=owner)

        assert second.status_code == _HTTP_OK


class TestPreferences:
    async def test_defaults_are_all_enabled(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        response = await client.get(PREFERENCES_URL, headers=owner)

        assert response.json() == {
            "price_changes": True,
            "risk_alerts": True,
            "ai_suggestions": True,
            "market_updates": True,
        }

    async def test_a_partial_update_leaves_other_switches_alone(
        self, client: AsyncClient, owner: dict[str, str]
    ) -> None:
        response = await client.patch(PREFERENCES_URL, json={"risk_alerts": False}, headers=owner)

        body = response.json()
        assert body["risk_alerts"] is False
        assert body["price_changes"] is True


class TestOwnershipIsolation:
    async def test_notifications_never_cross_accounts(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1225000.00")

        response = await client.get(NOTIFICATIONS_URL, headers=intruder)

        assert response.json()["total"] == 0

    async def test_another_account_cannot_mark_read(
        self, client: AsyncClient, owner: dict[str, str], intruder: dict[str, str]
    ) -> None:
        vehicle_id = await _save_vehicle(client, owner)
        await _drop_price(client, owner, vehicle_id, "1225000.00")
        listed = await client.get(NOTIFICATIONS_URL, headers=owner)
        notification_id = listed.json()["items"][0]["id"]

        response = await client.post(
            f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=intruder
        )

        assert response.status_code == _HTTP_NOT_FOUND

    async def test_listing_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(NOTIFICATIONS_URL)

        assert response.status_code == _HTTP_UNAUTHORIZED
